"""Level-1 comparator: FFD with one bounded EP-anchored look-ahead insertion."""
from __future__ import annotations

from math import isfinite
from time import perf_counter
from typing import Any

from scipy.optimize import OptimizeResult

from ..contracts import AlgorithmOutcome, AttemptStatistics, ConstructionTerminationReason
from ..feasibility import FixedOrientationFeasibilityPolicy, PlacementFeasibilityPolicy
from ..orientation import OrientationProvider, fixed_orientation_provider
from ...schemas import Container, Item, Placement, SolveResult
from .extreme_point_core import (
    ContainerState, SearchStats, _complete_attempt, _deadline_reached, _incomplete_attempt,
    _candidate_points, candidate_placement, constructive_search, place_candidate,
    resolved_item_order, selected_policy_allows,
)
from .container_subset_selection import ContainerSubsetSelectionPolicy, FixedContainerSubsetSelectionPolicy
from .gap_fill import GapFillSettings, GapFillStatistics, rank_constrained_points


def _first_fit(states: list[ContainerState], item: Item, tolerance: float, stats: SearchStats,
               policy: PlacementFeasibilityPolicy, provider: OrientationProvider):
    for state in states:
        for point in _candidate_points(state, item, provider.candidates(item)[0], None):
            for dimensions in provider.candidates(item):
                if _deadline_reached(stats):
                    return None
                stats.extreme_points_evaluated += 1
                stats.orientation_candidates_evaluated += 1
                candidate = candidate_placement(state, item, point, dimensions)
                if selected_policy_allows(state, candidate, tolerance, policy):
                    return state, candidate
    return None


def _pack(items: list[Item], containers: tuple[Container, ...], tolerance: float, stats: SearchStats,
          policy: PlacementFeasibilityPolicy, provider: OrientationProvider, gap: GapFillSettings,
          gap_stats: GapFillStatistics):
    states = [ContainerState(container) for container in containers]
    queue = list(items)
    while queue:
        if _deadline_reached(stats):
            return _incomplete_attempt(items, 0, containers, states, "extreme_point_ffd_gap_fill",
                ConstructionTerminationReason.TIME_LIMIT_REACHED, AttemptStatistics())
        head = queue.pop(0)
        chosen = _first_fit(states, head, tolerance, stats, policy, provider)
        if chosen is None:
            reason = ConstructionTerminationReason.TIME_LIMIT_REACHED if stats.time_limit_reached else ConstructionTerminationReason.NO_FEASIBLE_CANDIDATE
            return _incomplete_attempt(items, 0, containers, states, "extreme_point_ffd_gap_fill", reason, AttemptStatistics())
        place_candidate(chosen[0], chosen[1], tolerance)
        gap_stats.realized_item_order.append(head.item_id)
        ranked = rank_constrained_points(states)
        gap_stats.constrained_points_detected += len(ranked)
        ranked = ranked[:gap.max_constrained_points_per_step]
        gap_stats.constrained_points_considered += len(ranked)
        best: tuple[tuple[float, ...], int, ContainerState, Placement] | None = None
        step_candidates = 0
        # queue[0] is the new head and must be placed by canonical FFD on the
        # next main iteration.  Gap Fill may only bypass it with a later item.
        limit = min(len(queue) - 1, gap.lookahead_window_size - 1, gap.maximum_reorder_distance)
        for distance in range(1, limit + 1):
            item = queue[distance]
            for constrained in ranked:
                state = states[constrained.state_index]
                for orientation_rank, dimensions in enumerate(provider.candidates(item)):
                    if step_candidates >= gap.max_candidates_per_step or _deadline_reached(stats):
                        break
                    candidate = candidate_placement(state, item, constrained.point, dimensions)
                    gap_stats.candidates_evaluated += 1
                    step_candidates += 1
                    stats.extreme_points_evaluated += 1
                    stats.orientation_candidates_evaluated += 1
                    if not selected_policy_allows(state, candidate, tolerance, policy):
                        continue
                    gap_stats.candidates_feasible += 1
                    occupied = state.placements + [candidate]
                    max_x = max(value.x_mm + value.length_mm for value in occupied)
                    max_y = max(value.y_mm + value.width_mm for value in occupied)
                    max_z = max(value.z_mm + value.height_mm for value in occupied)
                    growth = max_x * max_y * max_z / (state.container.length_mm * state.container.width_mm * state.container.height_mm)
                    waste = sum(max(0.0, c - d) / total for c, d, total in zip(constrained.clearance_mm, (candidate.length_mm, candidate.width_mm, candidate.height_mm), (state.container.length_mm, state.container.width_mm, state.container.height_mm)))
                    score = (growth, waste, float(distance), float(orientation_rank), float(constrained.state_index), candidate.z_mm, candidate.y_mm, candidate.x_mm, item.item_id)
                    if best is None or score < best[0]:
                        best = (score, distance, state, candidate)
                if step_candidates >= gap.max_candidates_per_step or stats.time_limit_reached:
                    break
            if step_candidates >= gap.max_candidates_per_step or stats.time_limit_reached:
                break
        if stats.time_limit_reached:
            return _incomplete_attempt(items, 0, containers, states, "extreme_point_ffd_gap_fill", ConstructionTerminationReason.TIME_LIMIT_REACHED, AttemptStatistics())
        if best is not None:
            _, distance, state, candidate = best
            item = queue.pop(distance)
            place_candidate(state, candidate, tolerance)
            gap_stats.insertions += 1
            gap_stats.max_reorder_distance = max(gap_stats.max_reorder_distance, distance)
            gap_stats.realized_item_order.append(item.item_id)
    return _complete_attempt(items, containers, states, "extreme_point_ffd_gap_fill", AttemptStatistics())


def solve(items: list[Item], containers: list[Container], settings: dict[str, Any] | None = None,
          *, policy: PlacementFeasibilityPolicy | None = None, orientation_provider: OrientationProvider | None = None,
          container_subset_policy: ContainerSubsetSelectionPolicy | None = None) -> AlgorithmOutcome:
    settings = settings or {}
    tolerance = float(settings.get("coordinate_tolerance_mm", 1e-6))
    gap = GapFillSettings.from_mapping(settings.get("gap_fill"))
    provider = orientation_provider or fixed_orientation_provider()
    selected_policy = policy or FixedOrientationFeasibilityPolicy()
    deadline = settings.get("constructive_deadline_monotonic")
    if deadline is None:
        deadline = perf_counter() + float(settings.get("gap_fill_time_limit_seconds", 30.0)) - float(settings.get("gap_fill_validation_reserve_seconds", 2.0))
    if not isinstance(deadline, (int, float)) or not isfinite(float(deadline)):
        raise ValueError("Gap Fill construction deadline must be finite")
    ordered = resolved_item_order(items, settings)
    aggregate_stats = GapFillStatistics()
    def pack_order(values, subset, tol, search_stats, selected, preference):
        del preference
        return _pack(values, subset, tol, search_stats, selected, provider, gap, aggregate_stats)
    selected_subset_policy = container_subset_policy
    if selected_subset_policy is None and bool(settings.get("fixed_subset", True)):
        selected_subset_policy = FixedContainerSubsetSelectionPolicy()
    search = constructive_search(ordered, containers, tolerance, int(settings.get("subset_enumeration_limit", 1)), pack_order, selected_policy,
        deadline_monotonic=float(deadline), container_subset_policy=selected_subset_policy)
    if search.time_limit_reached:
        result = SolveResult(status="TIME_LIMIT", message="EP-FFD Gap Fill reached its construction deadline.", objective_value=None, vector=None, raw_result=OptimizeResult())
    elif search.placements is None:
        result = SolveResult(status="INFEASIBLE_HEURISTIC", message="EP-FFD Gap Fill found no complete packing; this is not a proof of infeasibility.", objective_value=None, vector=None, raw_result=OptimizeResult())
    else:
        used = {value.container_id for value in search.placements}
        priority = 1.0 + sum(value.cost for value in containers)
        result = SolveResult(status="FEASIBLE", message="Deterministic EP-FFD Gap Fill found a complete packing.", objective_value=len(used) * priority + sum(value.cost for value in containers if value.container_id in used), vector=None, raw_result=OptimizeResult())
    return AlgorithmOutcome(result, [] if search.placements is None else search.placements, "deterministic/extreme-point-ffd-gap-fill", {
        "algorithm_kind": "constructive_heuristic_comparator", "item_ordering": "decreasing_volume_max_dimension_weight", "point_ordering": "ep_anchored_lookahead", "n_items": len(items), "n_containers": len(containers), "construction_time_limit_reached": search.time_limit_reached,
        **gap.metadata(), **aggregate_stats.metadata(), **provider.metadata(), **selected_policy.metadata(),
        **({} if selected_subset_policy is None else selected_subset_policy.metadata()),
        "candidate_subsets_evaluated": search.stats.candidate_subsets_evaluated, "packing_attempts": search.stats.packing_attempts,
        "extreme_points_evaluated": search.stats.extreme_points_evaluated, "orientation_candidates_evaluated": search.stats.orientation_candidates_evaluated,
        **({} if search.attempt is None else search.attempt.metadata()),
    })


solve_level1 = solve
