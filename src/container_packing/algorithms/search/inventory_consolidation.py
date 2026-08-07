"""Thử đóng bớt container bằng rebuild deterministic có giới hạn."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import combinations
from time import perf_counter
from typing import Any, Callable, Protocol

from ..contracts import AlgorithmOutcome
from ..feasibility import placements_overlap
from ...schemas import Container, Item, Placement
from ...geometry.support import evaluate_support
from .configuration import ConsolidationConfiguration, ContainerSearchConfiguration
from .inventory import InventorySearchLimits
from .subset_generation import LazyRankedContainerSubsetPolicy


ConsolidationExecutor = Callable[..., AlgorithmOutcome]
CandidateValidator = Callable[[list[Placement]], bool]


class SupportClosureProvider(Protocol):
    """Trả về item gốc cùng mọi dependent phải được di chuyển theo."""

    def __call__(
        self, placements: list[Placement],
    ) -> dict[str, frozenset[str]]: ...


@dataclass
class _ExactSubsetPolicy:
    subset: tuple[Container, ...]

    def __post_init__(self) -> None:
        self.generated = 0

    def candidates(
        self, containers: list[Container], items: list[Item],
    ) -> Iterable[tuple[Container, ...]]:
        del containers, items
        self.generated = 1
        yield self.subset

    def metadata(self) -> dict[str, object]:
        return {
            "container_subset_policy": "fixed_incumbent_subset",
            "container_subset_candidates_generated": self.generated,
            "container_subset_ids": [value.container_id for value in self.subset],
        }


@dataclass(frozen=True)
class DestinationCompatibility:
    container_id: str
    length_mm: float
    width_mm: float
    height_mm: float
    payload_slack_kg: float
    volume_slack_m3: float
    dimension_compatible_item_count: int
    extreme_point_compatible_count: int
    score: tuple[object, ...]

    def metadata(self) -> dict[str, object]:
        return {
            "container_id": self.container_id,
            "dimensions_mm": [self.length_mm, self.width_mm, self.height_mm],
            "payload_slack_kg": self.payload_slack_kg,
            "volume_slack_m3": self.volume_slack_m3,
            "dimension_compatible_item_count": self.dimension_compatible_item_count,
            "extreme_point_compatible_count": self.extreme_point_compatible_count,
        }


@dataclass(frozen=True)
class _EliminationRepackSpec:
    phase: str
    target_container_id: str
    destination_container_ids: tuple[str, ...]
    repack_item_ids: frozenset[str]
    item_order: tuple[str, ...]
    neighborhood_size: int
    order_mode: str
    closure_expansion_count: int
    signature: str


@dataclass
class _CappedSubsetPolicy:
    delegate: LazyRankedContainerSubsetPolicy
    limit: int

    def __post_init__(self) -> None:
        self.generated = 0

    def candidates(
        self, containers: list[Container], items: list[Item],
    ) -> Iterable[tuple[Container, ...]]:
        for subset in self.delegate.candidates(containers, items):
            if self.generated >= self.limit:
                break
            self.generated += 1
            yield subset

    def metadata(self) -> dict[str, object]:
        return {
            **self.delegate.metadata(),
            "container_subset_global_candidate_cap": self.limit,
            "container_subset_candidates_generated": self.generated,
        }


@dataclass(frozen=True)
class ConsolidationResult:
    outcome: AlgorithmOutcome
    metadata: dict[str, object]


class BoundedInventoryConsolidator:
    """Rebuild toàn bộ instance trên cardinality nhỏ hơn.

    Component chỉ thay đổi item order và subset search. Feasibility policy vẫn do
    executor của level cung cấp; independent validator vẫn là gate cuối ở pipeline.
    """

    def __init__(self, *, monotonic_clock: Callable[[], float] = perf_counter) -> None:
        self._clock = monotonic_clock

    def execute(
        self,
        *,
        baseline: AlgorithmOutcome,
        items: list[Item],
        containers: list[Container],
        settings: dict[str, Any],
        search: ContainerSearchConfiguration,
        aggregate_lower_bound: int,
        executor: ConsolidationExecutor,
        global_deadline_monotonic: float | None = None,
        support_closure_provider: SupportClosureProvider | None = None,
        candidate_validator: CandidateValidator | None = None,
    ) -> ConsolidationResult:
        config = search.consolidation
        initial_ids = {value.container_id for value in baseline.placements}
        initial_count = len(initial_ids)
        initial_utilization = _utilization_evidence(
            baseline, containers, prefix="incumbent_initial",
        )
        metadata: dict[str, object] = {
            **config.metadata(),
            **_empty_elimination_metadata(config),
            "container_elimination_initial_count": initial_count,
            "container_elimination_final_count": initial_count,
            "container_consolidation_attempted": False,
            "container_consolidation_initial_count": initial_count,
            "container_consolidation_final_count": initial_count,
            "container_consolidation_aggregate_lower_bound": aggregate_lower_bound,
            "container_consolidation_target_cardinalities": [],
            "container_consolidation_variants_attempted": [],
            "container_consolidation_candidates_evaluated": 0,
            "container_consolidation_closed_container_ids": [],
            "container_consolidation_runtime_seconds": 0.0,
            "container_consolidation_termination_reason": "disabled",
            "incumbent_initial_container_count": initial_count,
            "incumbent_final_container_count": initial_count,
            "incumbent_improvement_count": 0,
            "incumbent_gap_to_capacity_lower_bound": max(
                0, initial_count - aggregate_lower_bound,
            ),
            "incumbent_improvement_target_cardinalities": [],
            **initial_utilization,
            **_utilization_evidence(
                baseline, containers, prefix="incumbent_final",
            ),
        }
        if not config.enabled:
            return ConsolidationResult(baseline, metadata)
        if baseline.solve.status != "FEASIBLE" or not baseline.placements:
            metadata["container_consolidation_termination_reason"] = "baseline_not_complete"
            return ConsolidationResult(baseline, metadata)
        if initial_count <= aggregate_lower_bound:
            metadata["container_consolidation_termination_reason"] = "already_at_lower_bound"
            metadata["container_elimination_termination_reason"] = "already_at_lower_bound"
            return ConsolidationResult(baseline, metadata)

        started = self._clock()
        phase_deadline = started + config.time_limit_seconds
        deadline = (
            phase_deadline
            if global_deadline_monotonic is None
            else min(phase_deadline, global_deadline_monotonic)
        )
        selected = baseline
        elimination_metadata = _empty_elimination_metadata(config)
        if config.container_elimination.enabled:
            selected, elimination_metadata = self._run_container_elimination(
                baseline=baseline,
                items=items,
                containers=containers,
                settings=settings,
                executor=executor,
                deadline=deadline,
                support_closure_provider=(
                    support_closure_provider or singleton_support_closures
                ),
                candidate_validator=candidate_validator,
                config=config,
            )
        elimination_ids = {value.container_id for value in selected.placements}
        if len(elimination_ids) <= aggregate_lower_bound:
            metadata.update({
                **elimination_metadata,
                "container_consolidation_attempted": True,
                "container_consolidation_final_count": len(elimination_ids),
                "container_consolidation_closed_container_ids": sorted(
                    initial_ids - elimination_ids
                ),
                "container_consolidation_runtime_seconds": self._clock() - started,
                "container_consolidation_termination_reason": "valid_consolidated",
                "incumbent_final_container_count": len(elimination_ids),
                "incumbent_improvement_count": initial_count - len(elimination_ids),
                "incumbent_gap_to_capacity_lower_bound": 0,
                **_utilization_evidence(
                    selected, containers, prefix="incumbent_final",
                ),
            })
            return ConsolidationResult(selected, metadata)

        incumbent_count = len(elimination_ids)
        target_minimum = aggregate_lower_bound
        target_maximum = incumbent_count - 1
        # Descend from the incumbent so a hard lower bound cannot consume the
        # whole budget before easier one-container reductions are attempted.
        targets = list(range(target_maximum, target_minimum - 1, -1))
        metadata["container_consolidation_attempted"] = True
        metadata["container_consolidation_target_cardinalities"] = targets

        selected_ids = elimination_ids
        candidates_evaluated = 0
        variants_attempted: list[dict[str, object]] = []
        # `decreasing_volume` is the canonical constructor order and therefore
        # duplicates `current`. Keep `current` because construction only probes
        # a bounded portfolio and may not have refined this exact cardinality.
        variants = [
            value for value in config.item_order_variants
            if value != "decreasing_volume"
        ]
        attempts = [
            (target, variant) for target in targets for variant in variants
        ]
        for attempt_index, (target, variant) in enumerate(attempts):
            if self._clock() >= deadline or candidates_evaluated >= config.max_candidates:
                break
            attempts_left = len(attempts) - attempt_index
            remaining_candidates = config.max_candidates - candidates_evaluated
            attempt_candidate_budget = max(
                1, remaining_candidates // max(attempts_left, 1),
            )
            now = self._clock()
            attempt_deadline = now + (deadline - now) / max(attempts_left, 1)
            limits = InventorySearchLimits(
                initial_used_container_count=target,
                max_used_container_count=target,
                automatically_increase_container_count=False,
            )
            delegate = LazyRankedContainerSubsetPolicy(
                limits,
                exhaustive_max_containers=search.exhaustive_max_containers,
                max_candidates_per_count=min(
                    search.max_candidates_per_count, attempt_candidate_budget,
                ),
                neighborhood_width=search.neighborhood_width,
                composition_beam_width=search.composition_beam_width,
                soft_volume_buffer_ratio=search.soft_volume_buffer_ratio,
                deadline_monotonic=attempt_deadline,
                monotonic_clock=self._clock,
            )
            policy = _CappedSubsetPolicy(delegate, attempt_candidate_budget)
            selected_settings = dict(settings)
            if variant != "current":
                selected_settings["item_order_override"] = inventory_item_order(
                    items, variant,
                )
            selected_settings["constructive_deadline_monotonic"] = attempt_deadline
            candidate = executor(
                items,
                containers,
                selected_settings,
                container_subset_policy=policy,
            )
            candidates_evaluated += policy.generated
            candidate_ids = {value.container_id for value in candidate.placements}
            variants_attempted.append({
                "target_cardinality": target,
                "item_order": variant,
                "status": candidate.solve.status,
                "candidate_count": policy.generated,
                "used_container_count": len(candidate_ids),
                "attempt_deadline_monotonic": attempt_deadline,
            })
            if (
                candidate.solve.status == "FEASIBLE"
                and candidate.placements
                and _rank(candidate, containers) < _rank(selected, containers)
            ):
                selected = candidate
                selected_ids = candidate_ids
                # The subset policy searches cardinalities in ascending order;
                # reaching the aggregate lower bound cannot be improved further.
                if len(selected_ids) <= aggregate_lower_bound:
                    break

        runtime = self._clock() - started
        final_count = len(selected_ids)
        timed_out = self._clock() >= deadline
        metadata.update({
            **elimination_metadata,
            "container_consolidation_final_count": final_count,
            "container_consolidation_variants_attempted": variants_attempted,
            "container_consolidation_candidates_evaluated": candidates_evaluated,
            "container_consolidation_closed_container_ids": sorted(initial_ids - selected_ids),
            "container_consolidation_runtime_seconds": runtime,
            "container_consolidation_termination_reason": (
                "valid_consolidated" if final_count < initial_count
                else "consolidation_time_limit" if timed_out
                else "candidate_limit" if candidates_evaluated >= config.max_candidates
                else "heuristic_consolidation_failed"
            ),
            "incumbent_initial_container_count": initial_count,
            "incumbent_final_container_count": final_count,
            "incumbent_improvement_count": initial_count - final_count,
            "incumbent_gap_to_capacity_lower_bound": (
                final_count - aggregate_lower_bound
            ),
            "incumbent_improvement_target_cardinalities": targets,
            **_utilization_evidence(
                selected, containers, prefix="incumbent_final",
            ),
        })
        return ConsolidationResult(selected, metadata)

    def _run_container_elimination(
        self,
        *,
        baseline: AlgorithmOutcome,
        items: list[Item],
        containers: list[Container],
        settings: dict[str, Any],
        executor: ConsolidationExecutor,
        deadline: float,
        support_closure_provider: SupportClosureProvider,
        candidate_validator: CandidateValidator | None,
        config: ConsolidationConfiguration,
    ) -> tuple[AlgorithmOutcome, dict[str, object]]:
        """Đóng container bằng seeded relocation trước khi fallback full rebuild."""
        elimination = config.container_elimination
        adaptive = elimination.adaptive_cluster_elimination
        started = self._clock()
        total_window = max(0.0, deadline - started)
        phase_names = ("relocation", "support_closure", "partial_repack")
        phase_deadlines: list[float] = []
        cumulative = 0.0
        for fraction in elimination.phase_time_fractions:
            cumulative += fraction
            phase_deadlines.append(started + total_window * cumulative)

        selected = baseline
        item_by_id = {value.item_id: value for value in items}
        container_by_id = {value.container_id: value for value in containers}
        attempts: list[dict[str, object]] = []
        rejection_counts: dict[str, int] = defaultdict(int)
        phase_counts = {name: 0 for name in phase_names}
        accepted: list[dict[str, object]] = []
        candidates = 0
        target_ids_considered: list[str] = []
        failed_items_by_target: dict[str, str] = {}
        destination_rankings: dict[str, list[dict[str, object]]] = {}
        neighborhood_sizes_attempted: set[int] = set()
        duplicate_signatures: set[str] = set()
        duplicate_candidates_skipped = 0
        closure_expansion_count = 0

        for phase_index, phase in enumerate(phase_names):
            phase_deadline = min(deadline, phase_deadlines[phase_index])
            if self._clock() >= phase_deadline:
                continue
            target_limit = elimination.maximum_target_containers
            if phase == "partial_repack" and adaptive.enabled:
                target_limit = min(
                    target_limit, adaptive.maximum_target_containers,
                )
            ranked_targets = _rank_elimination_targets(
                selected.placements, containers,
            )[:target_limit]
            adaptive_per_target_cap = max(
                1, adaptive.maximum_candidates // max(len(ranked_targets), 1),
            )
            for target_id in ranked_targets:
                if (
                    self._clock() >= phase_deadline
                    or candidates >= elimination.maximum_candidates
                ):
                    break
                if target_id not in {
                    value.container_id for value in selected.placements
                }:
                    continue
                if target_id not in target_ids_considered:
                    target_ids_considered.append(target_id)
                remaining_container_ids = sorted({
                    value.container_id for value in selected.placements
                    if value.container_id != target_id
                })
                if not remaining_container_ids:
                    rejection_counts["no_destination_container"] += 1
                    continue
                subset = tuple(
                    container_by_id[value] for value in remaining_container_ids
                )
                target_placements = [
                    value for value in selected.placements
                    if value.container_id == target_id
                ]
                if phase == "partial_repack" and adaptive.enabled:
                    compatibilities = rank_destination_compatibility(
                        target_placements=target_placements,
                        all_placements=selected.placements,
                        containers=subset,
                        item_by_id=item_by_id,
                        failed_item_id=failed_items_by_target.get(target_id),
                    )
                    destination_rankings[target_id] = [
                        value.metadata() for value in compatibilities
                    ]
                    if not _aggregate_destination_capacity_sufficient(
                        target_placements, compatibilities,
                    ):
                        rejection_counts[
                            "no_destination_with_aggregate_capacity"
                        ] += 1
                        continue
                    specs = adaptive_cluster_repack_specs(
                        placements=selected.placements,
                        target_id=target_id,
                        compatibilities=compatibilities,
                        item_by_id=item_by_id,
                        support_closure_provider=support_closure_provider,
                        failed_item_id=failed_items_by_target.get(target_id),
                        maximum_destination_containers=(
                            adaptive.maximum_destination_containers
                        ),
                        neighborhood_sizes=adaptive.neighborhood_sizes,
                        beam_width=adaptive.beam_width,
                    )[:adaptive_per_target_cap]
                else:
                    basic = _basic_elimination_repack_spec(
                        selected.placements,
                        target_id=target_id,
                        phase=phase,
                        support_closure_provider=support_closure_provider,
                    )
                    specs = [] if basic is None else [basic]
                if not specs:
                    rejection_counts["no_bounded_neighborhood"] += 1
                    continue
                for spec in specs:
                    if (
                        self._clock() >= phase_deadline
                        or candidates >= elimination.maximum_candidates
                    ):
                        break
                    if spec.signature in duplicate_signatures:
                        duplicate_candidates_skipped += 1
                        continue
                    duplicate_signatures.add(spec.signature)
                    neighborhood_sizes_attempted.add(spec.neighborhood_size)
                    closure_expansion_count += spec.closure_expansion_count
                    repack_ids = set(spec.repack_item_ids)
                    item_order = list(spec.item_order)
                    seeds = tuple(
                        value for value in selected.placements
                        if value.item_id not in repack_ids
                        and value.container_id != target_id
                    )
                    repack_items = [item_by_id[value] for value in item_order]
                    policy = _ExactSubsetPolicy(subset)
                    selected_settings = dict(settings)
                    selected_settings["construction_initial_placements"] = seeds
                    selected_settings["item_order_override"] = item_order
                    selected_settings["constructive_deadline_monotonic"] = phase_deadline
                    candidate = executor(
                        repack_items,
                        containers,
                        selected_settings,
                        container_subset_policy=policy,
                    )
                    candidates += 1
                    phase_counts[phase] += 1
                    candidate_ids = {
                        value.container_id for value in candidate.placements
                    }
                    failed_item = candidate.metadata.get(
                        "construction_failed_item_id"
                    )
                    if failed_item:
                        failed_items_by_target[target_id] = str(failed_item)
                    row = {
                        "phase": phase,
                        "target_container_id": target_id,
                        "destination_container_ids": list(
                            spec.destination_container_ids
                        ),
                        "neighborhood_size": spec.neighborhood_size,
                        "order_mode": spec.order_mode,
                        "closure_expansion_count": spec.closure_expansion_count,
                        "repack_item_count": len(repack_ids),
                        "seeded_placement_count": len(seeds),
                        "status": candidate.solve.status,
                        "used_container_count": len(candidate_ids),
                        "failed_item_id": failed_item,
                        "best_partial_placement_count": candidate.metadata.get(
                            "best_partial_placement_count", 0,
                        ),
                        "geometry_rejections": candidate.metadata.get(
                            "geometry_rejected_candidates", 0,
                        ),
                        "boundary_rejections": candidate.metadata.get(
                            "boundary_rejected_candidates", 0,
                        ),
                        "overlap_rejections": candidate.metadata.get(
                            "overlap_rejected_candidates", 0,
                        ),
                        "payload_rejections": candidate.metadata.get(
                            "payload_rejected_candidates", 0,
                        ),
                        "support_rejections": candidate.metadata.get(
                            "support_rejected_candidates", 0,
                        ),
                    }
                    if candidate.solve.status != "FEASIBLE":
                        rejection_counts[str(candidate.solve.status).lower()] += 1
                        attempts.append(row)
                        continue
                    if len(candidate.placements) != len(items):
                        rejection_counts["incomplete_candidate"] += 1
                        row["validation_status"] = "INCOMPLETE"
                        attempts.append(row)
                        continue
                    if candidate_validator is not None and not candidate_validator(
                        candidate.placements
                    ):
                        rejection_counts["independent_validation_failed"] += 1
                        row["validation_status"] = "INVALID"
                        attempts.append(row)
                        continue
                    row["validation_status"] = "VALID"
                    if _rank(candidate, containers) < _rank(selected, containers):
                        previous_count = len({
                            value.container_id for value in selected.placements
                        })
                        selected = AlgorithmOutcome(
                            solve=candidate.solve,
                            placements=candidate.placements,
                            backend=candidate.backend,
                            metadata={
                                **candidate.metadata,
                                "n_items": len(items),
                                "n_containers": len(containers),
                            },
                        )
                        row["accepted"] = True
                        accepted.append({
                            "phase": phase,
                            "closed_container_id": target_id,
                            "destination_container_ids": list(
                                spec.destination_container_ids
                            ),
                            "neighborhood_size": spec.neighborhood_size,
                            "order_mode": spec.order_mode,
                            "container_count_before": previous_count,
                            "container_count_after": len(candidate_ids),
                        })
                        attempts.append(row)
                        break
                    rejection_counts["not_better_than_incumbent"] += 1
                    row["accepted"] = False
                    attempts.append(row)

        final_ids = {value.container_id for value in selected.placements}
        initial_ids = {value.container_id for value in baseline.placements}
        timed_out = self._clock() >= deadline
        return selected, {
            "container_elimination_attempted": candidates > 0,
            "container_elimination_target_container_ids": target_ids_considered,
            "container_elimination_phase_candidates": phase_counts,
            "container_elimination_candidates_evaluated": candidates,
            "container_elimination_attempts": attempts,
            "container_elimination_rejection_counts": dict(rejection_counts),
            "container_elimination_accepted_moves": accepted,
            "adaptive_cluster_destination_rankings": destination_rankings,
            "adaptive_cluster_failed_items_by_target": failed_items_by_target,
            "adaptive_cluster_neighborhood_sizes_attempted": sorted(
                neighborhood_sizes_attempted
            ),
            "adaptive_cluster_closure_expansion_count": closure_expansion_count,
            "adaptive_cluster_duplicate_candidates_skipped": (
                duplicate_candidates_skipped
            ),
            "container_elimination_closed_container_ids": sorted(
                initial_ids - final_ids
            ),
            "container_elimination_initial_count": len(initial_ids),
            "container_elimination_final_count": len(final_ids),
            "container_elimination_runtime_seconds": self._clock() - started,
            "container_elimination_termination_reason": (
                "VALID_CLUSTER_ELIMINATION" if len(final_ids) < len(initial_ids)
                else "TIME_LIMIT_WITH_INCUMBENT_PRESERVED" if timed_out
                else "CANDIDATE_LIMIT" if candidates >= elimination.maximum_candidates
                else "NO_VALID_CLUSTER_REPACK"
            ),
        }


def inventory_item_order(items: list[Item], variant: str) -> list[str]:
    if variant == "decreasing_volume":
        key = lambda value: (
            -value.volume_m3,
            -max(value.length_mm, value.width_mm, value.height_mm),
            -value.weight_kg,
            value.item_id,
        )
    elif variant == "decreasing_weight":
        key = lambda value: (-value.weight_kg, -value.volume_m3, value.item_id)
    elif variant == "support_difficulty":
        key = lambda value: (
            -(value.length_mm * value.width_mm),
            -value.weight_kg,
            -value.height_mm,
            value.item_id,
        )
    else:  # guarded by configuration parsing
        raise ValueError(f"Unsupported consolidation item order: {variant}")
    return [value.item_id for value in sorted(items, key=key)]


def singleton_support_closures(
    placements: list[Placement],
) -> dict[str, frozenset[str]]:
    """Level 1 không có support graph: mỗi item là một closure độc lập."""
    return {
        value.item_id: frozenset((value.item_id,)) for value in placements
    }


def exact_support_closures(
    placements: list[Placement], *, epsilon_mm: float,
) -> dict[str, frozenset[str]]:
    """Dựng transitive supporter→dependent closure từ incumbent Level 2."""
    dependents: dict[str, set[str]] = defaultdict(set)
    for placement in placements:
        support = evaluate_support(
            placement, placements, epsilon_mm=epsilon_mm,
        )
        for supporter_id in support.supporting_item_ids:
            dependents[supporter_id].add(placement.item_id)

    closures: dict[str, frozenset[str]] = {}
    for placement in placements:
        root = placement.item_id
        pending = [root]
        reached: set[str] = set()
        while pending:
            item_id = pending.pop()
            if item_id in reached:
                continue
            reached.add(item_id)
            pending.extend(sorted(dependents.get(item_id, ()), reverse=True))
        closures[root] = frozenset(reached)
    return closures


def _empty_elimination_metadata(
    config: ConsolidationConfiguration,
) -> dict[str, object]:
    return {
        **config.container_elimination.metadata(),
        "container_elimination_attempted": False,
        "container_elimination_target_container_ids": [],
        "container_elimination_phase_candidates": {
            "relocation": 0, "support_closure": 0, "partial_repack": 0,
        },
        "container_elimination_candidates_evaluated": 0,
        "container_elimination_attempts": [],
        "container_elimination_rejection_counts": {},
        "container_elimination_accepted_moves": [],
        "adaptive_cluster_destination_rankings": {},
        "adaptive_cluster_failed_items_by_target": {},
        "adaptive_cluster_neighborhood_sizes_attempted": [],
        "adaptive_cluster_closure_expansion_count": 0,
        "adaptive_cluster_duplicate_candidates_skipped": 0,
        "container_elimination_closed_container_ids": [],
        "container_elimination_initial_count": 0,
        "container_elimination_final_count": 0,
        "container_elimination_runtime_seconds": 0.0,
        "container_elimination_termination_reason": (
            "not_started" if config.container_elimination.enabled else "disabled"
        ),
    }


def _rank_elimination_targets(
    placements: list[Placement], containers: list[Container],
) -> list[str]:
    by_container: dict[str, list[Placement]] = defaultdict(list)
    for placement in placements:
        by_container[placement.container_id].append(placement)
    costs = {value.container_id: value.cost for value in containers}
    return [
        container_id for container_id, _ in sorted(
            by_container.items(),
            key=lambda entry: (
                len(entry[1]),
                sum(value.volume_m3 for value in entry[1]),
                sum(value.weight_kg for value in entry[1]),
                -costs.get(entry[0], 0.0),
                entry[0],
            ),
        )
    ]


def _basic_elimination_repack_spec(
    placements: list[Placement],
    *,
    target_id: str,
    phase: str,
    support_closure_provider: SupportClosureProvider,
 ) -> _EliminationRepackSpec | None:
    target = [value for value in placements if value.container_id == target_id]
    if not target:
        return None
    target_ids = {value.item_id for value in target}
    closures = support_closure_provider(placements)
    repack_ids = set(target_ids)

    placement_by_id = {value.item_id: value for value in placements}
    if phase == "relocation":
        ordered = sorted(
            repack_ids,
            key=lambda item_id: (
                placement_by_id[item_id].z_mm,
                -placement_by_id[item_id].volume_m3,
                item_id,
            ),
        )
    else:
        # Supporter phải được dựng trước dependent. z của incumbent là một
        # topological order deterministic cho fixed-orientation support graph.
        ordered = sorted(
            repack_ids,
            key=lambda item_id: (
                placement_by_id[item_id].z_mm,
                placement_by_id[item_id].container_id,
                -placement_by_id[item_id].volume_m3,
                item_id,
            ),
        )
    order = tuple(ordered)
    return _EliminationRepackSpec(
        phase=phase,
        target_container_id=target_id,
        destination_container_ids=(),
        repack_item_ids=frozenset(repack_ids),
        item_order=order,
        neighborhood_size=0,
        order_mode=("source_z" if phase == "relocation" else "supporter_first"),
        closure_expansion_count=0,
        signature="|".join((phase, target_id, ",".join(order))),
    )


def rank_destination_compatibility(
    *,
    target_placements: list[Placement],
    all_placements: list[Placement],
    containers: tuple[Container, ...],
    item_by_id: dict[str, Item],
    failed_item_id: str | None,
) -> list[DestinationCompatibility]:
    """Xếp hạng destination bằng capacity và frontier geometry deterministic."""
    by_container: dict[str, list[Placement]] = defaultdict(list)
    for placement in all_placements:
        by_container[placement.container_id].append(placement)
    failed_item = item_by_id.get(failed_item_id or "")
    ranked: list[DestinationCompatibility] = []
    for container in containers:
        existing = by_container.get(container.container_id, [])
        loaded_weight = sum(value.weight_kg for value in existing)
        loaded_volume = sum(value.volume_m3 for value in existing)
        physical_volume = (
            container.volume_m3
            if container.volume_m3 > 0
            else container.length_mm * container.width_mm * container.height_mm
            / 1_000_000_000.0
        )
        dimension_compatible = sum(
            1 for placement in target_placements
            if placement.length_mm <= container.length_mm
            and placement.width_mm <= container.width_mm
            and placement.height_mm <= container.height_mm
        )
        ep_compatible = 0
        if failed_item is not None:
            for point in _frontier_points(container, existing):
                if (
                    point[0] + failed_item.length_mm <= container.length_mm
                    and point[1] + failed_item.width_mm <= container.width_mm
                    and point[2] + failed_item.height_mm <= container.height_mm
                ):
                    ep_compatible += 1
        payload_slack = container.max_weight_kg - loaded_weight
        volume_slack = physical_volume - loaded_volume
        score: tuple[object, ...] = (
            -dimension_compatible,
            -ep_compatible,
            -max(0.0, payload_slack),
            -max(0.0, volume_slack),
            container.container_id,
        )
        ranked.append(DestinationCompatibility(
            container.container_id,
            container.length_mm,
            container.width_mm,
            container.height_mm,
            payload_slack,
            volume_slack,
            dimension_compatible,
            ep_compatible,
            score,
        ))
    return sorted(ranked, key=lambda value: value.score)


def _aggregate_destination_capacity_sufficient(
    target_placements: list[Placement],
    compatibilities: list[DestinationCompatibility],
) -> bool:
    required_weight = sum(value.weight_kg for value in target_placements)
    required_volume = sum(value.volume_m3 for value in target_placements)
    return (
        sum(max(0.0, value.payload_slack_kg) for value in compatibilities)
        + 1e-9 >= required_weight
        and sum(max(0.0, value.volume_slack_m3) for value in compatibilities)
        + 1e-12 >= required_volume
        and max(
            (value.dimension_compatible_item_count for value in compatibilities),
            default=0,
        ) == len(target_placements)
    )


def adaptive_cluster_repack_specs(
    *,
    placements: list[Placement],
    target_id: str,
    compatibilities: list[DestinationCompatibility],
    item_by_id: dict[str, Item],
    support_closure_provider: SupportClosureProvider,
    failed_item_id: str | None,
    maximum_destination_containers: int,
    neighborhood_sizes: tuple[int, ...],
    beam_width: int,
) -> list[_EliminationRepackSpec]:
    """Sinh portfolio cluster nhỏ, tăng dần và không cắt support closure."""
    target = [value for value in placements if value.container_id == target_id]
    if not target:
        return []
    target_ids = {value.item_id for value in target}
    placement_by_id = {value.item_id: value for value in placements}
    closures = support_closure_provider(placements)
    selected_failed = failed_item_id if failed_item_id in item_by_id else max(
        target,
        key=lambda value: (
            value.volume_m3,
            max(value.length_mm, value.width_mm, value.height_mm),
            value.item_id,
        ),
    ).item_id
    failed_item = item_by_id[selected_failed]
    shortlist = compatibilities[:max(maximum_destination_containers * 2, 1)]
    cluster_ids: list[tuple[str, ...]] = []
    for size in range(1, min(maximum_destination_containers, len(shortlist)) + 1):
        cluster_ids.extend(
            tuple(value.container_id for value in group)
            for group in combinations(shortlist, size)
        )

    specs: list[_EliminationRepackSpec] = []
    modes = ("failed_first", "supporter_first", "decreasing_volume", "decreasing_footprint")
    for neighborhood_size in neighborhood_sizes:
        level_specs: list[_EliminationRepackSpec] = []
        for cluster in cluster_ids:
            blockers = _rank_failed_item_blockers(
                failed_item, cluster, placements,
                compatibility_by_id={
                    value.container_id: value for value in compatibilities
                },
            )
            repack_ids = set(target_ids)
            selected_root_count = 0
            for blocker in blockers:
                closure = set(closures.get(
                    blocker.item_id, frozenset((blocker.item_id,)),
                ))
                new_ids = closure - repack_ids
                if not new_ids:
                    continue
                current_extra = len(repack_ids - target_ids)
                if current_extra + len(new_ids) > neighborhood_size:
                    continue
                repack_ids.update(new_ids)
                selected_root_count += 1
            if not repack_ids - target_ids:
                continue
            closure_expansion = len(repack_ids - target_ids) - selected_root_count
            for mode in modes:
                order = _cluster_item_order(
                    repack_ids,
                    placement_by_id=placement_by_id,
                    item_by_id=item_by_id,
                    failed_item_id=selected_failed,
                    mode=mode,
                )
                signature = "|".join((
                    target_id,
                    ",".join(cluster),
                    ",".join(sorted(repack_ids)),
                    mode,
                ))
                level_specs.append(_EliminationRepackSpec(
                    phase="partial_repack",
                    target_container_id=target_id,
                    destination_container_ids=cluster,
                    repack_item_ids=frozenset(repack_ids),
                    item_order=order,
                    neighborhood_size=neighborhood_size,
                    order_mode=mode,
                    closure_expansion_count=max(0, closure_expansion),
                    signature=signature,
                ))
        level_specs.sort(key=lambda value: (
            len(value.destination_container_ids),
            len(value.repack_item_ids),
            value.destination_container_ids,
            value.order_mode,
            value.signature,
        ))
        specs.extend(level_specs[:beam_width])
    return specs


def _rank_failed_item_blockers(
    failed_item: Item,
    destination_ids: tuple[str, ...],
    placements: list[Placement],
    *,
    compatibility_by_id: dict[str, DestinationCompatibility],
) -> list[Placement]:
    blockers = [
        value for value in placements if value.container_id in destination_ids
    ]
    by_container: dict[str, list[Placement]] = defaultdict(list)
    for placement in blockers:
        by_container[placement.container_id].append(placement)
    conflict_counts: dict[str, int] = defaultdict(int)
    for container_id, existing in by_container.items():
        compatibility = compatibility_by_id[container_id]
        pseudo = Container(
            container_id,
            compatibility.length_mm,
            compatibility.width_mm,
            compatibility.height_mm,
            float("inf"), 0.0,
        )
        for x, y, z in _frontier_points(pseudo, existing):
            candidate = Placement(
                failed_item.item_id, container_id, x, y, z,
                failed_item.length_mm, failed_item.width_mm,
                failed_item.height_mm, failed_item.weight_kg,
            )
            for placement in existing:
                if placements_overlap(candidate, placement, 1e-6):
                    conflict_counts[placement.item_id] += 1
    return sorted(
        blockers,
        key=lambda value: (
            -conflict_counts.get(value.item_id, 0),
            -value.z_mm,
            value.volume_m3,
            value.container_id,
            value.item_id,
        ),
    )


def _frontier_points(
    container: Container, placements: list[Placement],
) -> tuple[tuple[float, float, float], ...]:
    points = {(0.0, 0.0, 0.0)}
    for value in placements:
        points.update({
            (value.x_mm + value.length_mm, value.y_mm, value.z_mm),
            (value.x_mm, value.y_mm + value.width_mm, value.z_mm),
            (value.x_mm, value.y_mm, value.z_mm + value.height_mm),
        })
    return tuple(sorted(
        (
            point for point in points
            if point[0] <= container.length_mm
            and point[1] <= container.width_mm
            and point[2] <= container.height_mm
            and not any(
                placement.x_mm <= point[0] < placement.x_mm + placement.length_mm
                and placement.y_mm <= point[1] < placement.y_mm + placement.width_mm
                and placement.z_mm <= point[2] < placement.z_mm + placement.height_mm
                for placement in placements
            )
        ),
        key=lambda value: (value[2], value[1], value[0]),
    ))


def _cluster_item_order(
    item_ids: set[str],
    *,
    placement_by_id: dict[str, Placement],
    item_by_id: dict[str, Item],
    failed_item_id: str,
    mode: str,
) -> tuple[str, ...]:
    if mode == "failed_first":
        key = lambda item_id: (
            0 if item_id == failed_item_id else 1,
            -item_by_id[item_id].volume_m3,
            item_id,
        )
    elif mode == "supporter_first":
        key = lambda item_id: (
            placement_by_id[item_id].z_mm,
            -item_by_id[item_id].volume_m3,
            item_id,
        )
    elif mode == "decreasing_volume":
        key = lambda item_id: (-item_by_id[item_id].volume_m3, item_id)
    elif mode == "decreasing_footprint":
        key = lambda item_id: (
            -(item_by_id[item_id].length_mm * item_by_id[item_id].width_mm),
            -item_by_id[item_id].height_mm,
            item_id,
        )
    else:
        raise ValueError(f"Unsupported adaptive cluster order mode: {mode}")
    return tuple(sorted(item_ids, key=key))


def _rank(outcome: AlgorithmOutcome, containers: list[Container]) -> tuple[int, float]:
    used = {value.container_id for value in outcome.placements}
    cost = sum(value.cost for value in containers if value.container_id in used)
    return len(used), cost


def _utilization_evidence(
    outcome: AlgorithmOutcome,
    containers: list[Container],
    *,
    prefix: str,
) -> dict[str, float]:
    used = {value.container_id for value in outcome.placements}
    selected = [value for value in containers if value.container_id in used]
    required_volume = sum(value.volume_m3 for value in outcome.placements)
    required_payload = sum(value.weight_kg for value in outcome.placements)
    available_volume = sum(value.volume_m3 for value in selected)
    available_payload = sum(value.max_weight_kg for value in selected)
    return {
        f"{prefix}_volume_utilization_ratio": (
            required_volume / available_volume if available_volume > 0 else 0.0
        ),
        f"{prefix}_payload_utilization_ratio": (
            required_payload / available_payload if available_payload > 0 else 0.0
        ),
        f"{prefix}_volume_slack_m3": max(0.0, available_volume - required_volume),
        f"{prefix}_payload_slack_kg": max(
            0.0, available_payload - required_payload,
        ),
    }
