"""Deterministic objective-aware Extreme-Point Best-Fit Decreasing heuristic."""

from __future__ import annotations

from typing import Any
from math import isfinite
from time import perf_counter

from scipy.optimize import OptimizeResult

from ..contracts import (
    AlgorithmOutcome,
    AttemptStatistics,
    ConstructionAttemptResult,
    ConstructionTerminationReason,
)
from ..feasibility import FixedOrientationFeasibilityPolicy, PlacementFeasibilityPolicy
from ..orientation import OrientationProvider, fixed_orientation_provider
from .extreme_point_core import (
    ContainerState,
    SearchStats,
    candidate_placement,
    constructive_search,
    item_sort_key,
    place_candidate,
    resolved_item_order,
    selected_policy_allows,
    _complete_attempt,
    _incomplete_attempt,
)
from .candidate_scoring import CandidateScoringPolicy
from .candidate_points import CandidatePointProvider
from .container_subset_selection import ContainerSubsetSelectionPolicy
from .container_assignment import (
    ContainerAssignmentPlanner,
    ContainerPreferencePolicy,
)
from ...schemas import Container, Item, Placement, SolveResult


def _bounding_volume(placements: list[Placement], candidate: Placement | None = None) -> float:
    if not placements and candidate is None:
        return 0.0
    max_x = max((value.x_mm + value.length_mm for value in placements), default=0.0)
    max_y = max((value.y_mm + value.width_mm for value in placements), default=0.0)
    max_z = max((value.z_mm + value.height_mm for value in placements), default=0.0)
    if candidate is not None:
        max_x = max(max_x, candidate.x_mm + candidate.length_mm)
        max_y = max(max_y, candidate.y_mm + candidate.width_mm)
        max_z = max(max_z, candidate.z_mm + candidate.height_mm)
    return max_x * max_y * max_z


def best_fit_candidate_score(
    state: ContainerState, candidate: Placement, container_rank: int,
) -> tuple[float, ...]:
    """Score one feasible placement; lower is better in objective-aware lexicographic order."""
    is_open = bool(state.placements)
    item_volume = candidate.length_mm * candidate.width_mm * candidate.height_mm
    container_volume = (
        state.container.length_mm * state.container.width_mm * state.container.height_mm
    )
    remaining_volume = container_volume - state.loaded_volume_mm3 - item_volume
    remaining_payload = state.container.max_weight_kg - state.loaded_weight_kg - candidate.weight_kg
    before = _bounding_volume(state.placements)
    after = _bounding_volume(state.placements, candidate)
    return (
        0.0 if is_open else 1.0,
        0.0 if is_open else float(state.container.cost),
        float(remaining_volume),
        float(remaining_payload),
        float(after - before),
        float(after),
        float(candidate.z_mm), float(candidate.y_mm), float(candidate.x_mm),
        float(container_rank),
    )


def pack_order_best_fit(
    items: list[Item], containers: tuple[Container, ...], tolerance: float, stats: SearchStats,
    policy: PlacementFeasibilityPolicy, *, orientation_provider: OrientationProvider | None = None,
    candidate_scoring_policy: CandidateScoringPolicy | None = None,
    candidate_point_provider: CandidatePointProvider | None = None,
    container_preference_policy: ContainerPreferencePolicy | None = None,
) -> ConstructionAttemptResult:
    """Place each item at the best feasible container/extreme-point candidate."""
    selected_provider = orientation_provider or fixed_orientation_provider()
    states = [ContainerState(container) for container in containers]
    start_candidates = stats.extreme_points_evaluated
    start_orientations = stats.orientation_candidates_evaluated
    attempt_containers_tested = 0
    for item_index, item in enumerate(items):
        containers_tested = 0
        candidates_tested = 0
        orientations_tested = 0
        if stats.time_limit_reached or (
            stats.deadline_monotonic is not None and perf_counter() >= stats.deadline_monotonic
        ):
            stats.time_limit_reached = True
            return _incomplete_attempt(
                items, item_index, containers, states, "extreme_point_best_fit",
                ConstructionTerminationReason.TIME_LIMIT_REACHED,
                AttemptStatistics(),
            )
        selected: tuple[tuple[float, ...], ContainerState, Placement] | None = None
        for container_rank, state in enumerate(states):
            if (
                container_preference_policy is not None
                and not container_preference_policy.allows(
                    item, state.container.container_id
                )
            ):
                continue
            containers_tested += 1
            attempt_containers_tested += 1
            if candidate_point_provider is None:
                candidates_iter = (
                    (point, dimensions)
                    for point in sorted(state.extreme_points, key=lambda value: (value[2], value[1], value[0]))
                    for dimensions in selected_provider.candidates(item)
                )
            else:
                candidates_iter = (
                    (point, dimensions)
                    for dimensions in selected_provider.candidates(item)
                    for point in candidate_point_provider.points(state, item, dimensions)
                )
            for point, dimensions in candidates_iter:
                if stats.deadline_monotonic is not None and perf_counter() >= stats.deadline_monotonic:
                    stats.time_limit_reached = True
                    return _incomplete_attempt(
                        items, item_index, containers, states, "extreme_point_best_fit",
                        ConstructionTerminationReason.TIME_LIMIT_REACHED,
                        AttemptStatistics(
                            containers_tested, candidates_tested, orientations_tested,
                        ),
                        AttemptStatistics(
                            attempt_containers_tested,
                            stats.extreme_points_evaluated - start_candidates,
                            stats.orientation_candidates_evaluated - start_orientations,
                        ),
                    )
                stats.extreme_points_evaluated += 1
                stats.orientation_candidates_evaluated += 1
                candidates_tested += 1
                orientations_tested += 1
                placement = candidate_placement(state, item, point, dimensions)
                if not selected_policy_allows(state, placement, tolerance, policy):
                    continue
                base_score = best_fit_candidate_score(state, placement, container_rank)
                candidate = (
                    base_score if candidate_scoring_policy is None else
                    candidate_scoring_policy.score(state, placement, container_rank, base_score)
                )
                if container_preference_policy is not None:
                    candidate = (
                        float(container_preference_policy.rank(
                            item, state.container.container_id
                        )),
                        *candidate,
                    )
                if selected is None or candidate < selected[0]:
                    selected = candidate, state, placement
        if selected is None:
            return _incomplete_attempt(
                items, item_index, containers, states, "extreme_point_best_fit",
                ConstructionTerminationReason.NO_FEASIBLE_CANDIDATE,
                AttemptStatistics(
                    containers_tested, candidates_tested, orientations_tested,
                ),
                AttemptStatistics(
                    attempt_containers_tested,
                    stats.extreme_points_evaluated - start_candidates,
                    stats.orientation_candidates_evaluated - start_orientations,
                ),
            )
        place_candidate(selected[1], selected[2], tolerance)
        if container_preference_policy is not None:
            container_preference_policy.record_selection(
                item, selected[1].container.container_id
            )
    return _complete_attempt(
        items, containers, states, "extreme_point_best_fit",
        AttemptStatistics(
            attempt_containers_tested,
            stats.extreme_points_evaluated - start_candidates,
            stats.orientation_candidates_evaluated - start_orientations,
        ),
    )


def solve(
    items: list[Item], containers: list[Container], settings: dict[str, Any] | None = None,
    *, policy: PlacementFeasibilityPolicy | None = None,
    orientation_provider: OrientationProvider | None = None,
    candidate_scoring_policy: CandidateScoringPolicy | None = None,
    candidate_point_provider: CandidatePointProvider | None = None,
    container_subset_policy: ContainerSubsetSelectionPolicy | None = None,
    container_assignment_planner: ContainerAssignmentPlanner | None = None,
) -> AlgorithmOutcome:
    """Pack all items with deterministic Best Fit; FEASIBLE is not proof of optimality."""
    settings = settings or {}
    tolerance = float(settings.get("coordinate_tolerance_mm", 1e-6))
    subset_limit = int(settings.get("subset_enumeration_limit", 12))
    if subset_limit <= 0:
        raise ValueError("subset_enumeration_limit must be positive")
    selected_policy = policy or FixedOrientationFeasibilityPolicy()
    selected_orientation_provider = orientation_provider or fixed_orientation_provider()
    deadline = settings.get("constructive_deadline_monotonic")
    if deadline is not None and (not isinstance(deadline, (int, float)) or not isfinite(float(deadline))):
        raise ValueError("constructive_deadline_monotonic must be a finite monotonic timestamp")
    ordered_items = resolved_item_order(items, settings)
    def pack_order(items, containers, tolerance, stats, policy, preference_policy):
        return pack_order_best_fit(
            items, containers, tolerance, stats, policy,
            orientation_provider=selected_orientation_provider,
            candidate_scoring_policy=candidate_scoring_policy,
            candidate_point_provider=candidate_point_provider,
            container_preference_policy=preference_policy,
        )
    search = constructive_search(
        ordered_items, containers, tolerance, subset_limit, pack_order, selected_policy,
        deadline_monotonic=None if deadline is None else float(deadline),
        container_subset_policy=container_subset_policy,
        container_assignment_planner=container_assignment_planner,
    )

    priority = 1.0 + sum(value.cost for value in containers)
    if search.time_limit_reached:
        solve = SolveResult(
            status="TIME_LIMIT",
            message="Extreme-Point Best Fit stopped because its construction deadline was reached.",
            objective_value=None, vector=None, raw_result=OptimizeResult(),
        )
    elif search.placements is None:
        solve = SolveResult(
            status="INFEASIBLE_HEURISTIC",
            message="Best-Fit heuristic found no complete packing; this is not a proof of infeasibility.",
            objective_value=None, vector=None, raw_result=OptimizeResult(),
        )
    else:
        used_ids = {value.container_id for value in search.placements}
        used_cost = sum(value.cost for value in containers if value.container_id in used_ids)
        objective = len(used_ids) * priority + used_cost
        solve = SolveResult(
            status="FEASIBLE",
            message="Deterministic Extreme-Point Best Fit found a complete packing.",
            objective_value=float(objective), vector=None, raw_result=OptimizeResult(),
        )
    return AlgorithmOutcome(
        solve=solve,
        placements=[] if search.placements is None else search.placements,
        backend="deterministic/extreme-point-best-fit",
        metadata={
            "algorithm_kind": "constructive_heuristic",
            "optimality_proven": False,
            "item_ordering": "decreasing_volume_max_dimension_weight",
            "point_ordering": "objective_aware_best_fit",
            "container_selection_strategy": "minimum_count_then_cost_subset_search",
            "candidate_scoring": (
                "open_container_then_incremental_cost_then_residual_volume_payload_"
                "then_bounding_growth_then_bottom_left_back"
            ),
            "subset_enumeration_limit": subset_limit,
            "candidate_subsets_evaluated": search.stats.candidate_subsets_evaluated,
            "packing_attempts": search.stats.packing_attempts,
            "extreme_points_evaluated": search.stats.extreme_points_evaluated,
            "orientation_candidates_evaluated": search.stats.orientation_candidates_evaluated,
            "candidate_container_ids": [value.container_id for value in search.chosen_containers],
            "n_items": len(items),
            "n_containers": len(containers),
            "construction_time_limit_reached": search.time_limit_reached,
            **({} if search.attempt is None else search.attempt.metadata()),
            **selected_orientation_provider.metadata(),
            **selected_policy.metadata(),
            **({} if candidate_scoring_policy is None else candidate_scoring_policy.metadata()),
            **({} if candidate_point_provider is None else candidate_point_provider.metadata()),
            **({} if container_subset_policy is None else container_subset_policy.metadata()),
            **(
                {}
                if container_subset_policy is None
                else {"container_subset_attempts": search.stats.subset_attempts}
            ),
            "container_assignment_plans_evaluated": search.stats.assignment_plans_evaluated,
            **search.stats.selected_assignment_metadata,
            **(
                {} if container_assignment_planner is None
                else container_assignment_planner.metadata()
            ),
        },
    )


solve_level1 = solve
