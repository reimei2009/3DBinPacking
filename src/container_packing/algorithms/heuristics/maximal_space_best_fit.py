"""Deterministic Maximal Empty Spaces Best-Fit heuristic."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from time import perf_counter
from typing import Any, Callable

from scipy.optimize import OptimizeResult

from ..contracts import (
    AlgorithmOutcome,
    AttemptStatistics,
    ConstructionAttemptResult,
    ConstructionTerminationReason,
    UnpackedItemDiagnostic,
)
from ..feasibility import FixedOrientationFeasibilityPolicy, PlacementFeasibilityPolicy
from ..orientation import OrientationProvider, fixed_orientation_provider
from .constructive_common import candidate_subsets, container_orders
from .container_subset_selection import ContainerSubsetSelectionPolicy
from .extreme_point_core import resolved_item_order
from .maximal_space_core import (
    EmptySpace,
    MaximalSpaceContainerState,
    MaximalSpaceStats,
    candidate_placement,
    feasible_in_state,
    initialized_maximal_space_states,
    occupied_bounding_volume,
    place_candidate,
    space_sort_key,
)
from .secondary_candidate_scoring import (
    SecondaryCandidateScoringPolicy,
    configured_secondary_candidate_policy,
)
from ...schemas import Container, Item, Placement, SolveResult


@dataclass(frozen=True)
class MaximalSpaceSearchResult:
    attempt: ConstructionAttemptResult | None
    chosen_containers: tuple[Container, ...]
    stats: MaximalSpaceStats

    @property
    def placements(self) -> list[Placement] | None:
        if self.attempt is None or not self.attempt.complete:
            return None
        return list(self.attempt.placements)


def candidate_score(
    state: MaximalSpaceContainerState,
    candidate: Placement,
    space: EmptySpace,
    container_rank: int,
) -> tuple[float, ...]:
    """Return the objective-aware Best-Fit score for a feasible MES candidate."""

    is_open = bool(state.placements)
    item_volume = candidate.length_mm * candidate.width_mm * candidate.height_mm
    container_volume = (
        state.container.length_mm * state.container.width_mm * state.container.height_mm
    )
    before = occupied_bounding_volume(state.placements)
    after = occupied_bounding_volume(state.placements, candidate=candidate)
    return (
        0.0 if is_open else 1.0,
        0.0 if is_open else float(state.container.cost),
        float(space.volume_mm3 - item_volume),
        float(container_volume - state.loaded_volume_mm3 - item_volume),
        float(state.container.max_weight_kg - state.loaded_weight_kg - candidate.weight_kg),
        float(after - before),
        float(after),
        float(space.z_mm), float(space.y_mm), float(space.x_mm),
        float(container_rank),
        float(space.length_mm), float(space.width_mm), float(space.height_mm),
    )


def _flatten(states: list[MaximalSpaceContainerState]) -> tuple[Placement, ...]:
    return tuple(value for state in states for value in state.placements)


def _attempt_signature(
    items: list[Item], containers: tuple[Container, ...],
) -> str:
    return "|".join((
        "maximal_space_best_fit",
        ",".join(value.container_id for value in containers),
        ",".join(value.item_id for value in items),
    ))


def _attempt(
    *,
    items: list[Item],
    failed_index: int | None,
    containers: tuple[Container, ...],
    states: list[MaximalSpaceContainerState],
    reason: ConstructionTerminationReason,
    start_spaces: int,
    start_orientations: int,
    stats: MaximalSpaceStats,
) -> ConstructionAttemptResult:
    placements = _flatten(states)
    complete = failed_index is None
    unpacked = () if complete else tuple(
        UnpackedItemDiagnostic(
            item_id=item.item_id,
            reason_code=str(
                reason if index == failed_index
                else ConstructionTerminationReason.NOT_ATTEMPTED_AFTER_FAILURE
            ),
        )
        for index, item in enumerate(items[failed_index:], start=failed_index)
    )
    return ConstructionAttemptResult(
        complete=complete,
        placements=placements,
        unpacked_items=unpacked,
        failed_item_id=None if complete else items[failed_index].item_id,
        termination_reason=str(reason),
        attempt_signature=_attempt_signature(items, containers),
        statistics=AttemptStatistics(
            containers_tested=len(containers) * (
                len(items) if complete else max(0, failed_index + 1)
            ),
            candidate_positions_tested=(
                stats.empty_spaces_evaluated - start_spaces
            ),
            orientations_tested=(
                stats.orientation_candidates_evaluated - start_orientations
            ),
        ),
        subset_ids=tuple(value.container_id for value in containers),
        container_order=tuple(value.container_id for value in containers),
        algorithm_id="maximal_space_best_fit",
        search_score=(
            None if complete else (float(len(unpacked)), -float(len(placements)))
        ),
    )


def pack_order(
    items: list[Item],
    containers: tuple[Container, ...],
    tolerance: float,
    stats: MaximalSpaceStats,
    policy: PlacementFeasibilityPolicy,
    *,
    orientation_provider: OrientationProvider | None = None,
    initial_placements: tuple[Placement, ...] = (),
    deadline_monotonic: float | None = None,
    monotonic_clock: Callable[[], float] = perf_counter,
    secondary_scoring_policy: SecondaryCandidateScoringPolicy | None = None,
) -> ConstructionAttemptResult:
    selected_orientation_provider = orientation_provider or fixed_orientation_provider()
    states = initialized_maximal_space_states(
        containers,
        initial_placements,
        tolerance=tolerance,
        policy=policy,
        stats=stats,
    )
    stats.maximum_active_spaces = max(stats.maximum_active_spaces, 1 if states else 0)
    start_spaces = stats.empty_spaces_evaluated
    start_orientations = stats.orientation_candidates_evaluated
    for item_index, item in enumerate(items):
        if deadline_monotonic is not None and monotonic_clock() >= deadline_monotonic:
            stats.time_limit_reached = True
            return _attempt(
                items=items, failed_index=item_index, containers=containers,
                states=states, reason=ConstructionTerminationReason.TIME_LIMIT_REACHED,
                start_spaces=start_spaces, start_orientations=start_orientations,
                stats=stats,
            )
        selected: tuple[
            tuple[float, ...], MaximalSpaceContainerState, Placement,
        ] | None = None
        for container_rank, state in enumerate(states):
            for space in sorted(state.empty_spaces, key=space_sort_key):
                for dimensions in selected_orientation_provider.candidates(item):
                    if (
                        deadline_monotonic is not None
                        and monotonic_clock() >= deadline_monotonic
                    ):
                        stats.time_limit_reached = True
                        return _attempt(
                            items=items, failed_index=item_index, containers=containers,
                            states=states,
                            reason=ConstructionTerminationReason.TIME_LIMIT_REACHED,
                            start_spaces=start_spaces,
                            start_orientations=start_orientations,
                            stats=stats,
                        )
                    stats.empty_spaces_evaluated += 1
                    stats.orientation_candidates_evaluated += 1
                    placement = candidate_placement(state, item, space, dimensions)
                    if not feasible_in_state(
                        state, item, space, tolerance, policy, dimensions,
                    ):
                        continue
                    score = candidate_score(state, placement, space, container_rank)
                    if secondary_scoring_policy is not None:
                        score = secondary_scoring_policy.score(
                            state, placement, container_rank, score,
                        )
                    if selected is None or score < selected[0]:
                        selected = score, state, placement
        if selected is None:
            return _attempt(
                items=items, failed_index=item_index, containers=containers,
                states=states, reason=ConstructionTerminationReason.NO_FEASIBLE_CANDIDATE,
                start_spaces=start_spaces, start_orientations=start_orientations,
                stats=stats,
            )
        place_candidate(selected[1], selected[2], stats, tolerance)
    return _attempt(
        items=items, failed_index=None, containers=containers, states=states,
        reason=ConstructionTerminationReason.COMPLETE,
        start_spaces=start_spaces, start_orientations=start_orientations,
        stats=stats,
    )


def search_container_subsets(
    ordered_items: list[Item],
    containers: list[Container],
    tolerance: float,
    subset_limit: int,
    policy: PlacementFeasibilityPolicy,
    *,
    orientation_provider: OrientationProvider | None = None,
    container_subset_policy: ContainerSubsetSelectionPolicy | None = None,
    initial_placements: tuple[Placement, ...] = (),
    deadline_monotonic: float | None = None,
    monotonic_clock: Callable[[], float] = perf_counter,
    secondary_scoring_policy: SecondaryCandidateScoringPolicy | None = None,
    contact_support_index_enabled: bool = False,
) -> MaximalSpaceSearchResult:
    stats = MaximalSpaceStats(
        contact_support_index_enabled=contact_support_index_enabled,
    )
    total_weight = sum(value.weight_kg for value in ordered_items) + sum(
        value.weight_kg for value in initial_placements
    )
    total_volume = sum(value.volume_m3 for value in ordered_items) + sum(
        value.volume_m3 for value in initial_placements
    )
    subsets = (
        candidate_subsets(containers, subset_limit)
        if container_subset_policy is None
        else container_subset_policy.candidates(containers, ordered_items)
    )
    best_partial: ConstructionAttemptResult | None = None
    best_containers: tuple[Container, ...] = ()
    for subset in subsets:
        if deadline_monotonic is not None and monotonic_clock() >= deadline_monotonic:
            stats.time_limit_reached = True
            break
        stats.candidate_subsets_evaluated += 1
        row: dict[str, object] = {
            "container_ids": [value.container_id for value in subset],
            "container_count": len(subset),
            "total_cost": sum(value.cost for value in subset),
            "status": "packing_failed",
        }
        if sum(value.max_weight_kg for value in subset) + tolerance < total_weight:
            row["status"] = "aggregate_payload_infeasible"
            stats.subset_attempts.append(row)
            continue
        if sum(value.volume_m3 for value in subset) + tolerance < total_volume:
            row["status"] = "aggregate_volume_infeasible"
            stats.subset_attempts.append(row)
            continue
        for order in container_orders(subset):
            stats.packing_attempts += 1
            attempt = pack_order(
                ordered_items, order, tolerance, stats, policy,
                orientation_provider=orientation_provider,
                initial_placements=initial_placements,
                deadline_monotonic=deadline_monotonic,
                monotonic_clock=monotonic_clock,
                secondary_scoring_policy=secondary_scoring_policy,
            )
            if (
                not attempt.complete
                and (best_partial is None or len(attempt.placements) > len(best_partial.placements))
            ):
                best_partial = attempt
                best_containers = order
            if stats.time_limit_reached:
                row["status"] = "time_limit"
                stats.subset_attempts.append(row)
                return MaximalSpaceSearchResult(attempt, order, stats)
            if attempt.complete:
                row["status"] = "feasible"
                stats.subset_attempts.append(row)
                return MaximalSpaceSearchResult(attempt, order, stats)
        stats.subset_attempts.append(row)
    return MaximalSpaceSearchResult(best_partial, best_containers, stats)


def solve(
    items: list[Item],
    containers: list[Container],
    settings: dict[str, Any] | None = None,
    *,
    policy: PlacementFeasibilityPolicy | None = None,
    orientation_provider: OrientationProvider | None = None,
    container_subset_policy: ContainerSubsetSelectionPolicy | None = None,
    monotonic_clock: Callable[[], float] = perf_counter,
) -> AlgorithmOutcome:
    """Pack all items using MES Best Fit; FEASIBLE does not prove optimality."""

    settings = settings or {}
    tolerance = float(settings.get("coordinate_tolerance_mm", 1e-6))
    subset_limit = int(settings.get("subset_enumeration_limit", 12))
    if subset_limit <= 0:
        raise ValueError("subset_enumeration_limit must be positive")
    deadline = settings.get("constructive_deadline_monotonic")
    if deadline is not None and (
        not isinstance(deadline, int | float) or not isfinite(float(deadline))
    ):
        raise ValueError(
            "constructive_deadline_monotonic must be a finite monotonic timestamp"
        )
    selected_policy = policy or FixedOrientationFeasibilityPolicy()
    selected_orientation_provider = orientation_provider or fixed_orientation_provider()
    ordered_items = resolved_item_order(items, settings)
    initial_raw = settings.get("construction_initial_placements", ())
    if not isinstance(initial_raw, list | tuple) or not all(
        isinstance(value, Placement) for value in initial_raw
    ):
        raise ValueError("construction_initial_placements must contain Placement values")
    initial_placements = tuple(initial_raw)
    seed_ids = [value.item_id for value in initial_placements]
    if len(seed_ids) != len(set(seed_ids)):
        raise ValueError("construction_initial_placements contains duplicate item IDs")
    if set(seed_ids) & {value.item_id for value in ordered_items}:
        raise ValueError(
            "construction_initial_placements and repack items must be disjoint"
        )
    # Chỉ dùng snapshot trước search để xác định thành phần KPI đang hoạt động.
    # Counter rejection/valid của policy phải được đọc lại sau search; nếu giữ
    # snapshot này đến output thì MES luôn báo 0 dù policy đã kiểm tra candidate.
    policy_contract_metadata = selected_policy.metadata()
    secondary_policy = configured_secondary_candidate_policy(
        settings,
        exact_support_active=str(
            policy_contract_metadata.get("feasibility_policy", "")
        ).endswith("exact_support"),
    )
    search = search_container_subsets(
        ordered_items,
        containers,
        tolerance,
        subset_limit,
        selected_policy,
        orientation_provider=selected_orientation_provider,
        container_subset_policy=container_subset_policy,
        initial_placements=initial_placements,
        deadline_monotonic=None if deadline is None else float(deadline),
        monotonic_clock=monotonic_clock,
        secondary_scoring_policy=secondary_policy,
        contact_support_index_enabled=bool(
            settings.get("contact_support_index", {}).get("enabled", False)
        ),
    )
    selected_policy_metadata = selected_policy.metadata()

    priority = 1.0 + sum(value.cost for value in containers)
    if search.stats.time_limit_reached:
        solve_result = SolveResult(
            status="TIME_LIMIT",
            message="Maximal-Space construction deadline was reached.",
            objective_value=None, vector=None, raw_result=OptimizeResult(),
        )
    elif search.placements is None:
        solve_result = SolveResult(
            status="INFEASIBLE_HEURISTIC",
            message=(
                "Maximal-Space heuristic found no complete packing; this is not "
                "a proof of infeasibility."
            ),
            objective_value=None, vector=None, raw_result=OptimizeResult(),
        )
    else:
        used_ids = {value.container_id for value in search.placements}
        used_cost = sum(
            value.cost for value in containers if value.container_id in used_ids
        )
        solve_result = SolveResult(
            status="FEASIBLE",
            message="Deterministic Maximal Empty Spaces Best Fit found a complete packing.",
            objective_value=float(len(used_ids) * priority + used_cost),
            vector=None,
            raw_result=OptimizeResult(),
        )
    attempt_metadata = {} if search.attempt is None else search.attempt.metadata()
    return AlgorithmOutcome(
        solve=solve_result,
        placements=[] if search.placements is None else search.placements,
        backend="deterministic/maximal-empty-spaces-best-fit",
        metadata={
            "algorithm_kind": "constructive_heuristic",
            "optimality_proven": False,
            "item_ordering": "decreasing_volume_max_dimension_weight",
            "space_representation": "maximal_empty_spaces_six_way_split",
            "container_selection_strategy": "minimum_count_then_cost_subset_search",
            "candidate_scoring": (
                "open_container_then_incremental_cost_then_space_waste_container_"
                "residual_payload_then_bounding_growth_then_bottom_left_back"
            ),
            "subset_enumeration_limit": subset_limit,
            "candidate_subsets_evaluated": search.stats.candidate_subsets_evaluated,
            "packing_attempts": search.stats.packing_attempts,
            "empty_spaces_evaluated": search.stats.empty_spaces_evaluated,
            "candidate_feasibility_checks": search.stats.empty_spaces_evaluated,
            "empty_spaces_generated": search.stats.empty_spaces_generated,
            "empty_spaces_pruned": search.stats.empty_spaces_pruned,
            "maximum_active_spaces": search.stats.maximum_active_spaces,
            "orientation_candidates_evaluated": (
                search.stats.orientation_candidates_evaluated
            ),
            "candidate_container_ids": [
                value.container_id for value in search.chosen_containers
            ],
            "container_subset_attempts": search.stats.subset_attempts[:128],
            "n_items": len(items),
            "n_containers": len(containers),
            "construction_initial_placement_count": len(initial_placements),
            "construction_time_limit_reached": search.stats.time_limit_reached,
            **attempt_metadata,
            **selected_orientation_provider.metadata(),
            **selected_policy_metadata,
            **search.stats.contact_support_metadata(),
            **({} if secondary_policy is None else secondary_policy.metadata()),
            **(
                {} if container_subset_policy is None
                else container_subset_policy.metadata()
            ),
        },
    )


solve_level1 = solve
