"""Thử đóng bớt container bằng rebuild deterministic có giới hạn."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import combinations
from time import perf_counter
from typing import Any, Callable, Protocol

from ..contracts import AlgorithmOutcome, SearchBudget
from ..feasibility import placements_overlap
from ..orientation import OrientationProvider, fixed_orientation_provider
from ...schemas import Container, Item, Placement
from ...geometry.support import evaluate_support
from .configuration import ConsolidationConfiguration, ContainerSearchConfiguration
from .inventory import InventorySearchLimits
from .incumbent import CandidateValidator, ValidatedIncumbentStore
from .subset_generation import LazyRankedContainerSubsetPolicy


ConsolidationExecutor = Callable[..., AlgorithmOutcome]


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
    existing_item_count: int
    score: tuple[object, ...]

    def metadata(self) -> dict[str, object]:
        return {
            "container_id": self.container_id,
            "dimensions_mm": [self.length_mm, self.width_mm, self.height_mm],
            "payload_slack_kg": self.payload_slack_kg,
            "volume_slack_m3": self.volume_slack_m3,
            "dimension_compatible_item_count": self.dimension_compatible_item_count,
            "extreme_point_compatible_count": self.extreme_point_compatible_count,
            "existing_item_count": self.existing_item_count,
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


@dataclass(frozen=True)
class AdaptiveClusterPortfolio:
    """Danh mục neighborhood đa tài nguyên cho một target container."""

    specs: tuple[_EliminationRepackSpec, ...]
    resource_anchor_ids: dict[str, tuple[str, ...]]
    cluster_sizes_generated: dict[int, int]
    cluster_sizes_selected: dict[int, int]
    cluster_count_generated: int
    cluster_count_selected: int

    def metadata(self) -> dict[str, object]:
        return {
            "resource_anchor_ids": {
                key: list(value) for key, value in self.resource_anchor_ids.items()
            },
            "cluster_sizes_generated": {
                str(key): value
                for key, value in sorted(self.cluster_sizes_generated.items())
            },
            "cluster_sizes_selected": {
                str(key): value
                for key, value in sorted(self.cluster_sizes_selected.items())
            },
            "cluster_count_generated": self.cluster_count_generated,
            "cluster_count_selected": self.cluster_count_selected,
        }


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
        incumbent_store: ValidatedIncumbentStore | None = None,
        search_budget: SearchBudget | None = None,
        orientation_provider: OrientationProvider | None = None,
    ) -> ConsolidationResult:
        config = search.consolidation
        active_orientation_provider = (
            orientation_provider or fixed_orientation_provider()
        )
        initial_ids = {value.container_id for value in baseline.placements}
        initial_count = len(initial_ids)
        initial_cost = _rank(baseline, containers)[1]
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
            "incumbent_initial_container_cost": initial_cost,
            "incumbent_final_container_cost": initial_cost,
            "incumbent_improvement_count": 0,
            "incumbent_gap_to_capacity_lower_bound": max(
                0, initial_count - aggregate_lower_bound,
            ),
            "incumbent_improvement_target_cardinalities": [],
            "container_consolidation_cardinalities_attempted": [],
            "container_consolidation_first_failed_cardinality": None,
            "container_consolidation_stepwise_descent": True,
            "container_consolidation_phase_runtime_seconds": {
                "local_repair": 0.0,
                "full_rebuild": 0.0,
            },
            **_lower_bound_pressure(items, containers, aggregate_lower_bound),
            **initial_utilization,
            **_utilization_evidence(
                baseline, containers, prefix="incumbent_final",
            ),
        }
        if not config.enabled:
            return ConsolidationResult(baseline, metadata)
        if incumbent_store is None:
            if candidate_validator is None:
                raise ValueError(
                    "Enabled consolidation requires an independent candidate_validator"
                )
            incumbent_store = ValidatedIncumbentStore(
                required_item_ids=[value.item_id for value in items],
                containers=containers,
                validator=candidate_validator,
            )
        if incumbent_store.outcome is None:
            incumbent_store.consider(baseline)
        if incumbent_store.outcome is None:
            metadata.update(incumbent_store.metadata())
            metadata["container_consolidation_termination_reason"] = (
                "baseline_not_independently_valid"
            )
            return ConsolidationResult(baseline, metadata)
        baseline = incumbent_store.outcome
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
        local_deadline = min(
            deadline,
            started
            + max(0.0, deadline - started)
            * config.improvement_phase_time_fractions[0],
        )
        selected = baseline
        elimination_metadata = _empty_elimination_metadata(config)
        local_started = self._clock()
        if config.container_elimination.enabled:
            selected, elimination_metadata = self._run_container_elimination(
                baseline=baseline,
                items=items,
                containers=containers,
                settings=settings,
                executor=executor,
                deadline=local_deadline,
                support_closure_provider=(
                    support_closure_provider or singleton_support_closures
                ),
                incumbent_store=incumbent_store,
                config=config,
                orientation_provider=active_orientation_provider,
            )
        local_runtime = self._clock() - local_started
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
                "incumbent_final_container_cost": _rank(selected, containers)[1],
                "incumbent_improvement_count": initial_count - len(elimination_ids),
                "incumbent_gap_to_capacity_lower_bound": 0,
                "container_consolidation_phase_runtime_seconds": {
                    "local_repair": local_runtime,
                    "full_rebuild": 0.0,
                },
                **_utilization_evidence(
                    selected, containers, prefix="incumbent_final",
                ),
                **incumbent_store.metadata(),
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
        cardinalities_attempted: list[int] = []
        first_failed_cardinality: int | None = None
        rebuild_started = self._clock()
        # `decreasing_volume` is the canonical constructor order and therefore
        # duplicates `current`. Keep `current` because construction only probes
        # a bounded portfolio and may not have refined this exact cardinality.
        variants = [
            value for value in config.item_order_variants
            if value != "decreasing_volume"
        ]
        target = target_maximum
        while target >= target_minimum:
            if self._clock() >= deadline or candidates_evaluated >= config.max_candidates:
                break
            cardinalities_attempted.append(target)
            target_improved = False
            for variant_index, variant in enumerate(variants):
                if (
                    self._clock() >= deadline
                    or candidates_evaluated >= config.max_candidates
                ):
                    break
                variants_left = len(variants) - variant_index
                remaining_candidates = config.max_candidates - candidates_evaluated
                attempt_candidate_budget = max(
                    1, remaining_candidates // max(variants_left, 1),
                )
                now = self._clock()
                attempt_deadline = now + (deadline - now) / max(variants_left, 1)
                limits = InventorySearchLimits(
                    initial_used_container_count=target,
                    max_used_container_count=target,
                    automatically_increase_container_count=False,
                )
                delegate = LazyRankedContainerSubsetPolicy(
                    limits,
                    orientation_provider=active_orientation_provider,
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
                attempt_started = self._clock()
                candidate = executor(
                    items,
                    containers,
                    selected_settings,
                    container_subset_policy=policy,
                )
                candidates_evaluated += policy.generated
                if search_budget is not None:
                    search_budget.record_repair()
                    search_budget.record_candidate(policy.generated)
                candidate_ids = {
                    value.container_id for value in candidate.placements
                }
                variants_attempted.append({
                    "target_cardinality": target,
                    "item_order": variant,
                    "status": candidate.solve.status,
                    "candidate_count": policy.generated,
                    "used_container_count": len(candidate_ids),
                    "attempt_deadline_monotonic": attempt_deadline,
                    "runtime_seconds": self._clock() - attempt_started,
                })
                row = variants_attempted[-1]
                if self._clock() >= deadline:
                    # Một constructor có thể vượt nhẹ deadline trước khi trả
                    # quyền điều khiển. Candidate đó chỉ là diagnostic; không
                    # được thay validated incumbent sau khi budget đã hết.
                    row["independent_validation_status"] = "NOT_RUN_DEADLINE"
                    break
                if candidate.solve.status != "FEASIBLE" or not candidate.placements:
                    row["independent_validation_status"] = "NOT_RUN"
                    continue
                if _rank(candidate, containers) >= _rank(selected, containers):
                    row["independent_validation_status"] = "NOT_BETTER"
                    continue
                invalid_before = incumbent_store.candidates_rejected_invalid
                if incumbent_store.consider(candidate):
                    selected = incumbent_store.outcome or selected
                    selected_ids = candidate_ids
                    row["independent_validation_status"] = "VALID"
                    row["accepted"] = True
                    target_improved = True
                    break
                row["independent_validation_status"] = (
                    "INVALID"
                    if incumbent_store.candidates_rejected_invalid > invalid_before
                    else "REJECTED"
                )
            if not target_improved:
                first_failed_cardinality = target
                break
            if len(selected_ids) <= aggregate_lower_bound:
                break
            target = len(selected_ids) - 1

        runtime = self._clock() - started
        final_count = len(selected_ids)
        timed_out = self._clock() >= deadline
        metadata.update({
            **elimination_metadata,
            "container_consolidation_final_count": final_count,
            "container_consolidation_variants_attempted": variants_attempted,
            "container_consolidation_candidates_evaluated": candidates_evaluated,
            "container_consolidation_cardinalities_attempted": cardinalities_attempted,
            "container_consolidation_first_failed_cardinality": first_failed_cardinality,
            "container_consolidation_phase_runtime_seconds": {
                "local_repair": local_runtime,
                "full_rebuild": self._clock() - rebuild_started,
            },
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
            "incumbent_initial_container_cost": initial_cost,
            "incumbent_final_container_cost": _rank(selected, containers)[1],
            "incumbent_improvement_count": initial_count - final_count,
            "incumbent_gap_to_capacity_lower_bound": (
                final_count - aggregate_lower_bound
            ),
            **incumbent_store.metadata(),
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
        incumbent_store: ValidatedIncumbentStore,
        config: ConsolidationConfiguration,
        orientation_provider: OrientationProvider,
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
        resource_anchor_ids: dict[str, dict[str, list[str]]] = {}
        target_failure_reasons: dict[str, str] = {}
        cluster_sizes_generated: dict[int, int] = defaultdict(int)
        cluster_sizes_selected: dict[int, int] = defaultdict(int)
        cluster_sizes_attempted: dict[int, int] = defaultdict(int)
        clusters_generated = 0
        clusters_selected = 0
        neighborhood_sizes_attempted: set[int] = set()
        duplicate_signatures: set[str] = set()
        duplicate_candidates_skipped = 0
        closure_expansion_count = 0
        phase_runtime_seconds: dict[str, float] = defaultdict(float)

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
                        orientation_provider=orientation_provider,
                    )
                    destination_rankings[target_id] = [
                        value.metadata() for value in compatibilities
                    ]
                    if not _aggregate_destination_capacity_sufficient(
                        target_placements, compatibilities,
                    ):
                        target_failure_reasons[target_id] = (
                            _aggregate_destination_failure_reason(
                                target_placements, compatibilities,
                            )
                        )
                        rejection_counts[
                            "no_destination_with_aggregate_capacity"
                        ] += 1
                        continue
                    portfolio = build_adaptive_cluster_repack_portfolio(
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
                        orientation_provider=orientation_provider,
                    )
                    specs = list(portfolio.specs)[:adaptive_per_target_cap]
                    if not specs:
                        target_failure_reasons[target_id] = (
                            "no_resource_diverse_partial_repack_candidate"
                        )
                    resource_anchor_ids[target_id] = {
                        key: list(value)
                        for key, value in portfolio.resource_anchor_ids.items()
                    }
                    for size, count in portfolio.cluster_sizes_generated.items():
                        cluster_sizes_generated[size] += count
                    for size, count in portfolio.cluster_sizes_selected.items():
                        cluster_sizes_selected[size] += count
                    clusters_generated += portfolio.cluster_count_generated
                    clusters_selected += portfolio.cluster_count_selected
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
                    cluster_sizes_attempted[
                        len(spec.destination_container_ids)
                    ] += 1
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
                    candidate_started = self._clock()
                    candidate = executor(
                        repack_items,
                        containers,
                        selected_settings,
                        container_subset_policy=policy,
                    )
                    candidate_runtime = self._clock() - candidate_started
                    phase_runtime_seconds[phase] += candidate_runtime
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
                        "runtime_seconds": candidate_runtime,
                    }
                    if self._clock() >= phase_deadline:
                        rejection_counts["deadline_after_candidate"] += 1
                        row["validation_status"] = "NOT_RUN_DEADLINE"
                        attempts.append(row)
                        break
                    if candidate.solve.status != "FEASIBLE":
                        rejection_counts[str(candidate.solve.status).lower()] += 1
                        attempts.append(row)
                        continue
                    if len(candidate.placements) != len(items):
                        rejection_counts["incomplete_candidate"] += 1
                        row["validation_status"] = "INCOMPLETE"
                        attempts.append(row)
                        continue
                    if _rank(candidate, containers) < _rank(selected, containers):
                        candidate = AlgorithmOutcome(
                            solve=candidate.solve,
                            placements=candidate.placements,
                            backend=candidate.backend,
                            metadata={
                                **candidate.metadata,
                                "n_items": len(items),
                                "n_containers": len(containers),
                            },
                        )
                        invalid_before = incumbent_store.candidates_rejected_invalid
                        if not incumbent_store.consider(candidate):
                            rejection_counts["independent_validation_failed"] += 1
                            row["validation_status"] = (
                                "INVALID"
                                if incumbent_store.candidates_rejected_invalid
                                > invalid_before
                                else "REJECTED"
                            )
                            attempts.append(row)
                            continue
                        row["validation_status"] = "VALID"
                        previous_count = len({
                            value.container_id for value in selected.placements
                        })
                        selected = incumbent_store.outcome or selected
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
                        target_failure_reasons.pop(target_id, None)
                        attempts.append(row)
                        break
                    rejection_counts["not_better_than_incumbent"] += 1
                    row["validation_status"] = "NOT_BETTER"
                    row["accepted"] = False
                    attempts.append(row)

        final_ids = {value.container_id for value in selected.placements}
        initial_ids = {value.container_id for value in baseline.placements}
        timed_out = self._clock() >= deadline
        accepted_targets = {
            str(value["closed_container_id"]) for value in accepted
        }
        for target_id in target_ids_considered:
            if target_id in accepted_targets or target_id in target_failure_reasons:
                continue
            target_rows = [
                value for value in attempts
                if value.get("target_container_id") == target_id
            ]
            target_failure_reasons[target_id] = _classify_target_failure(
                target_rows,
                timed_out=timed_out,
                candidate_limited=(candidates >= elimination.maximum_candidates),
            )
        return selected, {
            "container_elimination_attempted": candidates > 0,
            "container_elimination_target_container_ids": target_ids_considered,
            "container_elimination_phase_candidates": phase_counts,
            "container_elimination_candidates_evaluated": candidates,
            "container_elimination_attempts": attempts,
            "container_elimination_rejection_counts": dict(rejection_counts),
            "container_elimination_accepted_moves": accepted,
            "adaptive_cluster_destination_rankings": destination_rankings,
            "adaptive_cluster_resource_anchor_ids": resource_anchor_ids,
            "adaptive_cluster_cluster_sizes_generated": {
                str(key): value for key, value in sorted(
                    cluster_sizes_generated.items()
                )
            },
            "adaptive_cluster_cluster_sizes_selected": {
                str(key): value for key, value in sorted(
                    cluster_sizes_selected.items()
                )
            },
            "adaptive_cluster_cluster_sizes_attempted": {
                str(key): value for key, value in sorted(
                    cluster_sizes_attempted.items()
                )
            },
            "adaptive_cluster_clusters_generated": clusters_generated,
            "adaptive_cluster_clusters_selected": clusters_selected,
            "adaptive_cluster_failed_items_by_target": failed_items_by_target,
            "adaptive_cluster_failure_reason_by_target": target_failure_reasons,
            "adaptive_cluster_neighborhood_sizes_attempted": sorted(
                neighborhood_sizes_attempted
            ),
            "adaptive_cluster_closure_expansion_count": closure_expansion_count,
            "adaptive_cluster_duplicate_candidates_skipped": (
                duplicate_candidates_skipped
            ),
            "container_elimination_phase_runtime_seconds": {
                key: phase_runtime_seconds.get(key, 0.0)
                for key in phase_names
            },
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
        "container_elimination_phase_runtime_seconds": {
            "relocation": 0.0,
            "support_closure": 0.0,
            "partial_repack": 0.0,
        },
        "adaptive_cluster_destination_rankings": {},
        "adaptive_cluster_resource_anchor_ids": {},
        "adaptive_cluster_cluster_sizes_generated": {},
        "adaptive_cluster_cluster_sizes_selected": {},
        "adaptive_cluster_cluster_sizes_attempted": {},
        "adaptive_cluster_clusters_generated": 0,
        "adaptive_cluster_clusters_selected": 0,
        "adaptive_cluster_failed_items_by_target": {},
        "adaptive_cluster_failure_reason_by_target": {},
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
        # Relocation và support-closure cùng phá toàn bộ target container;
        # signature theo semantics giúp candidate trùng chỉ chạy một lần.
        signature="|".join(("basic_target_repack", target_id, ",".join(order))),
    )


def rank_destination_compatibility(
    *,
    target_placements: list[Placement],
    all_placements: list[Placement],
    containers: tuple[Container, ...],
    item_by_id: dict[str, Item],
    failed_item_id: str | None,
    orientation_provider: OrientationProvider | None = None,
) -> list[DestinationCompatibility]:
    """Xếp hạng destination bằng capacity và frontier geometry deterministic."""
    by_container: dict[str, list[Placement]] = defaultdict(list)
    for placement in all_placements:
        by_container[placement.container_id].append(placement)
    provider = orientation_provider or fixed_orientation_provider()
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
                if any(
                    point[0] + dimensions.length_mm <= container.length_mm
                    and point[1] + dimensions.width_mm <= container.width_mm
                    and point[2] + dimensions.height_mm <= container.height_mm
                    for dimensions in provider.candidates(failed_item)
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
            len(existing),
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


def _aggregate_destination_failure_reason(
    target_placements: list[Placement],
    compatibilities: list[DestinationCompatibility],
) -> str:
    """Giải thích hard aggregate prune, không tuyên bố geometric infeasibility."""
    if max(
        (value.dimension_compatible_item_count for value in compatibilities),
        default=0,
    ) < len(target_placements):
        return "dimension_compatibility"
    required_weight = sum(value.weight_kg for value in target_placements)
    required_volume = sum(value.volume_m3 for value in target_placements)
    payload_short = sum(
        max(0.0, value.payload_slack_kg) for value in compatibilities
    ) + 1e-9 < required_weight
    volume_short = sum(
        max(0.0, value.volume_slack_m3) for value in compatibilities
    ) + 1e-12 < required_volume
    if payload_short and volume_short:
        return "aggregate_payload_and_volume"
    if payload_short:
        return "aggregate_payload"
    if volume_short:
        return "aggregate_volume"
    return "aggregate_capacity_unknown"


def _classify_target_failure(
    attempts: list[dict[str, object]],
    *,
    timed_out: bool,
    candidate_limited: bool,
) -> str:
    """Phân loại diagnostic từ evidence đã có, không biến nó thành proof."""
    if timed_out or any(
        value.get("validation_status") == "NOT_RUN_DEADLINE"
        for value in attempts
    ):
        return "deadline"
    if candidate_limited:
        return "candidate_limit"
    rejection_totals = {
        "payload": sum(int(value.get("payload_rejections", 0)) for value in attempts),
        "support": sum(int(value.get("support_rejections", 0)) for value in attempts),
        "geometry": sum(
            int(value.get("geometry_rejections", 0))
            + int(value.get("boundary_rejections", 0))
            + int(value.get("overlap_rejections", 0))
            for value in attempts
        ),
    }
    strongest = max(
        rejection_totals,
        key=lambda key: (rejection_totals[key], key),
    )
    if rejection_totals[strongest] > 0:
        return strongest
    if any(value.get("failed_item_id") for value in attempts):
        return "construction_failed_item"
    return "no_valid_candidate_within_portfolio"


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
    orientation_provider: OrientationProvider | None = None,
) -> list[_EliminationRepackSpec]:
    """Compatibility wrapper trả spec từ canonical portfolio builder."""
    return list(build_adaptive_cluster_repack_portfolio(
        placements=placements,
        target_id=target_id,
        compatibilities=compatibilities,
        item_by_id=item_by_id,
        support_closure_provider=support_closure_provider,
        failed_item_id=failed_item_id,
        maximum_destination_containers=maximum_destination_containers,
        neighborhood_sizes=neighborhood_sizes,
        beam_width=beam_width,
        orientation_provider=(orientation_provider or fixed_orientation_provider()),
    ).specs)


def build_adaptive_cluster_repack_portfolio(
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
    orientation_provider: OrientationProvider | None = None,
) -> AdaptiveClusterPortfolio:
    """Sinh beam cluster đa tài nguyên, tăng dần và giữ support closure."""
    provider = orientation_provider or fixed_orientation_provider()
    target = [value for value in placements if value.container_id == target_id]
    if not target:
        return AdaptiveClusterPortfolio((), {}, {}, {}, 0, 0)
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
    shortlist, anchors = _resource_diverse_destination_shortlist(
        compatibilities,
        target_placements=target,
        maximum_destination_containers=maximum_destination_containers,
    )
    compatibility_by_id = {
        value.container_id: value for value in compatibilities
    }
    required_weight = sum(value.weight_kg for value in target)
    required_volume = sum(value.volume_m3 for value in target)
    ranked_clusters: dict[
        int, list[tuple[tuple[object, ...], tuple[str, ...]]]
    ] = defaultdict(list)
    for size in range(1, min(maximum_destination_containers, len(shortlist)) + 1):
        for group in combinations(shortlist, size):
            cluster = tuple(value.container_id for value in group)
            ranked_clusters[size].append((
                _destination_cluster_score(
                    group,
                    target_item_count=len(target),
                    required_weight=required_weight,
                    required_volume=required_volume,
                ),
                cluster,
            ))
        ranked_clusters[size].sort(key=lambda value: (value[0], value[1]))

    cluster_sizes_generated = {
        size: len(values) for size, values in ranked_clusters.items()
    }
    selected_cluster_signatures: set[tuple[str, ...]] = set()

    specs: list[_EliminationRepackSpec] = []
    modes = ("failed_first", "supporter_first", "decreasing_volume", "decreasing_footprint")
    for neighborhood_size in neighborhood_sizes:
        by_size: dict[
            int, list[tuple[tuple[object, ...], _EliminationRepackSpec]]
        ] = defaultdict(list)
        for cluster_size, cluster_values in ranked_clusters.items():
            for cluster_score, cluster in cluster_values:
                blockers = _rank_failed_item_blockers(
                    failed_item, cluster, placements,
                    compatibility_by_id=compatibility_by_id,
                    orientation_provider=provider,
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
                closure_expansion = (
                    len(repack_ids - target_ids) - selected_root_count
                )
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
                    spec = _EliminationRepackSpec(
                        phase="partial_repack",
                        target_container_id=target_id,
                        destination_container_ids=cluster,
                        repack_item_ids=frozenset(repack_ids),
                        item_order=order,
                        neighborhood_size=neighborhood_size,
                        order_mode=mode,
                        closure_expansion_count=max(0, closure_expansion),
                        signature=signature,
                    )
                    by_size[cluster_size].append((
                        (
                            *cluster_score,
                            len(repack_ids),
                            mode,
                            signature,
                        ),
                        spec,
                    ))
        for values in by_size.values():
            values.sort(key=lambda value: value[0])
        selected_level = _stratified_cluster_specs(
            by_size, beam_width=beam_width,
        )
        for spec in selected_level:
            selected_cluster_signatures.add(spec.destination_container_ids)
        specs.extend(selected_level)

    selected_sizes: dict[int, int] = defaultdict(int)
    for cluster in selected_cluster_signatures:
        selected_sizes[len(cluster)] += 1
    return AdaptiveClusterPortfolio(
        tuple(specs), anchors, cluster_sizes_generated, dict(selected_sizes),
        sum(cluster_sizes_generated.values()), len(selected_cluster_signatures),
    )


def _resource_diverse_destination_shortlist(
    compatibilities: list[DestinationCompatibility],
    *,
    target_placements: list[Placement],
    maximum_destination_containers: int,
) -> tuple[list[DestinationCompatibility], dict[str, tuple[str, ...]]]:
    """Giữ cả destination sẵn EP và destination cần phá nhưng giàu tài nguyên."""
    take = max(1, maximum_destination_containers)
    required_weight = max(
        sum(value.weight_kg for value in target_placements), 1e-9,
    )
    required_volume = max(
        sum(value.volume_m3 for value in target_placements), 1e-12,
    )
    rankings = {
        "frontier_ready": sorted(compatibilities, key=lambda value: (
            -value.extreme_point_compatible_count,
            -value.dimension_compatible_item_count,
            value.container_id,
        )),
        "payload_rich": sorted(compatibilities, key=lambda value: (
            -max(0.0, value.payload_slack_kg),
            -max(0.0, value.volume_slack_m3),
            value.container_id,
        )),
        "volume_rich": sorted(compatibilities, key=lambda value: (
            -max(0.0, value.volume_slack_m3),
            -max(0.0, value.payload_slack_kg),
            value.container_id,
        )),
        "blocker_repack": sorted(compatibilities, key=lambda value: (
            0 if value.existing_item_count > 0 else 1,
            0 if value.extreme_point_compatible_count == 0 else 1,
            -min(1.0, max(0.0, value.payload_slack_kg) / required_weight)
            -min(1.0, max(0.0, value.volume_slack_m3) / required_volume),
            value.existing_item_count,
            value.container_id,
        )),
    }
    anchors = {
        role: tuple(value.container_id for value in values[:take])
        for role, values in rankings.items()
    }
    # Portfolio phải đa dạng nhưng vẫn bounded: lấy round-robin theo từng
    # resource role thay vì hợp toàn bộ ``4 * take`` anchor. Với ba đích,
    # shortlist tối đa sáu container chỉ sinh 41 cluster thay vì 298 cluster
    # của shortlist 12 container, tránh planner tự trở thành bottleneck.
    shortlist_limit = max(4, take * 2)
    selected: dict[str, DestinationCompatibility] = {}
    for rank in range(take):
        for role in ("frontier_ready", "payload_rich", "volume_rich", "blocker_repack"):
            values = rankings[role]
            if rank >= len(values):
                continue
            value = values[rank]
            selected.setdefault(value.container_id, value)
            if len(selected) >= shortlist_limit:
                break
        if len(selected) >= shortlist_limit:
            break
    return list(selected.values()), anchors


def _destination_cluster_score(
    cluster: tuple[DestinationCompatibility, ...],
    *,
    target_item_count: int,
    required_weight: float,
    required_volume: float,
) -> tuple[object, ...]:
    payload = sum(max(0.0, value.payload_slack_kg) for value in cluster)
    volume = sum(max(0.0, value.volume_slack_m3) for value in cluster)
    payload_deficit = max(0.0, required_weight - payload) / max(
        required_weight, 1e-9,
    )
    volume_deficit = max(0.0, required_volume - volume) / max(
        required_volume, 1e-12,
    )
    payload_coverage = min(1.0, payload / max(required_weight, 1e-9))
    volume_coverage = min(1.0, volume / max(required_volume, 1e-12))
    resource_complementarity_gap = abs(payload_coverage - volume_coverage)
    return (
        0 if payload_deficit == 0.0 and volume_deficit == 0.0 else 1,
        0 if max(
            value.dimension_compatible_item_count for value in cluster
        ) == target_item_count else 1,
        max(payload_deficit, volume_deficit),
        payload_deficit + volume_deficit,
        resource_complementarity_gap,
        sum(value.existing_item_count for value in cluster),
        -sum(value.extreme_point_compatible_count for value in cluster),
        tuple(value.container_id for value in cluster),
    )


def _stratified_cluster_specs(
    specs_by_size: dict[
        int, list[tuple[tuple[object, ...], _EliminationRepackSpec]]
    ],
    *,
    beam_width: int,
) -> list[_EliminationRepackSpec]:
    """Round-robin theo cluster size để cluster nhiều đích không bị starvation."""
    queues = {
        size: list(values) for size, values in sorted(specs_by_size.items())
        if values
    }
    selected: list[_EliminationRepackSpec] = []
    while queues and len(selected) < beam_width:
        exhausted: list[int] = []
        for size in sorted(queues):
            if len(selected) >= beam_width:
                break
            values = queues[size]
            _, spec = values.pop(0)
            selected.append(spec)
            if not values:
                exhausted.append(size)
        for size in exhausted:
            queues.pop(size, None)
    return selected


def _rank_failed_item_blockers(
    failed_item: Item,
    destination_ids: tuple[str, ...],
    placements: list[Placement],
    *,
    compatibility_by_id: dict[str, DestinationCompatibility],
    orientation_provider: OrientationProvider,
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
            candidates = [
                Placement(
                    failed_item.item_id, container_id, x, y, z,
                    dimensions.length_mm, dimensions.width_mm,
                    dimensions.height_mm, failed_item.weight_kg,
                    orientation_code=dimensions.code,
                )
                for dimensions in orientation_provider.candidates(failed_item)
            ]
            for placement in existing:
                if candidates and all(
                    placements_overlap(candidate, placement, 1e-6)
                    for candidate in candidates
                ):
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


def _lower_bound_pressure(
    items: list[Item], containers: list[Container], aggregate_lower_bound: int,
) -> dict[str, object]:
    """Ước lượng mức sử dụng bắt buộc tại cận aggregate theo từng tài nguyên.

    Hai capacity được tối đa hóa độc lập nên đây vẫn là evidence lạc quan,
    không phải chứng minh tồn tại một subset hay một packing hình học khả thi.
    """
    count = max(0, min(aggregate_lower_bound, len(containers)))
    required_volume = sum(value.volume_m3 for value in items)
    required_payload = sum(value.weight_kg for value in items)
    attainable_volume = sum(sorted(
        (value.volume_m3 for value in containers), reverse=True,
    )[:count])
    attainable_payload = sum(sorted(
        (value.max_weight_kg for value in containers), reverse=True,
    )[:count])
    volume_ratio = (
        required_volume / attainable_volume if attainable_volume > 0 else 0.0
    )
    payload_ratio = (
        required_payload / attainable_payload if attainable_payload > 0 else 0.0
    )
    return {
        "lower_bound_capacity_pressure_model": (
            "independent_optimistic_resource_capacity_v1"
        ),
        "lower_bound_required_volume_utilization_ratio": volume_ratio,
        "lower_bound_required_payload_utilization_ratio": payload_ratio,
        "lower_bound_binding_resource": (
            "payload" if payload_ratio >= volume_ratio else "volume"
        ),
    }


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
