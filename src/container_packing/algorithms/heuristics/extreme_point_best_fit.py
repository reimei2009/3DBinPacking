"""Deterministic objective-aware Extreme-Point Best-Fit Decreasing heuristic."""

from __future__ import annotations

from typing import Any

from scipy.optimize import OptimizeResult

from ..contracts import AlgorithmOutcome
from ..feasibility import FixedOrientationFeasibilityPolicy, PlacementFeasibilityPolicy
from .extreme_point_core import (
    ContainerState,
    Point,
    SearchStats,
    constructive_search,
    fits,
    item_sort_key,
    place_item,
)
from ...schemas import Container, Item, Placement, SolveResult


def _bounding_volume(placements: list[Placement], item: Item | None = None, point: Point | None = None) -> float:
    if not placements and item is None:
        return 0.0
    max_x = max((value.x_mm + value.length_mm for value in placements), default=0.0)
    max_y = max((value.y_mm + value.width_mm for value in placements), default=0.0)
    max_z = max((value.z_mm + value.height_mm for value in placements), default=0.0)
    if item is not None and point is not None:
        max_x = max(max_x, point[0] + item.length_mm)
        max_y = max(max_y, point[1] + item.width_mm)
        max_z = max(max_z, point[2] + item.height_mm)
    return max_x * max_y * max_z


def best_fit_candidate_score(
    state: ContainerState, item: Item, point: Point, container_rank: int,
) -> tuple[float, ...]:
    """Score one feasible placement; lower is better in objective-aware lexicographic order."""
    is_open = bool(state.placements)
    item_volume = item.length_mm * item.width_mm * item.height_mm
    container_volume = (
        state.container.length_mm * state.container.width_mm * state.container.height_mm
    )
    remaining_volume = container_volume - state.loaded_volume_mm3 - item_volume
    remaining_payload = state.container.max_weight_kg - state.loaded_weight_kg - item.weight_kg
    before = _bounding_volume(state.placements)
    after = _bounding_volume(state.placements, item, point)
    return (
        0.0 if is_open else 1.0,
        0.0 if is_open else float(state.container.cost),
        float(remaining_volume),
        float(remaining_payload),
        float(after - before),
        float(after),
        float(point[2]), float(point[1]), float(point[0]),
        float(container_rank),
    )


def pack_order_best_fit(
    items: list[Item], containers: tuple[Container, ...], tolerance: float, stats: SearchStats,
    policy: PlacementFeasibilityPolicy,
) -> list[Placement] | None:
    """Place each item at the best feasible container/extreme-point candidate."""
    states = [ContainerState(container) for container in containers]
    for item in items:
        selected: tuple[tuple[float, ...], ContainerState, Point] | None = None
        for container_rank, state in enumerate(states):
            for point in sorted(state.extreme_points, key=lambda value: (value[2], value[1], value[0])):
                stats.extreme_points_evaluated += 1
                if not fits(state, item, point, tolerance, policy):
                    continue
                candidate = best_fit_candidate_score(state, item, point, container_rank)
                if selected is None or candidate < selected[0]:
                    selected = candidate, state, point
        if selected is None:
            return None
        place_item(selected[1], item, selected[2], tolerance)
    return [placement for state in states for placement in state.placements]


def solve(
    items: list[Item], containers: list[Container], settings: dict[str, Any] | None = None,
    *, policy: PlacementFeasibilityPolicy | None = None,
) -> AlgorithmOutcome:
    """Pack all items with deterministic Best Fit; FEASIBLE is not proof of optimality."""
    settings = settings or {}
    tolerance = float(settings.get("coordinate_tolerance_mm", 1e-6))
    subset_limit = int(settings.get("subset_enumeration_limit", 12))
    if subset_limit <= 0:
        raise ValueError("subset_enumeration_limit must be positive")
    selected_policy = policy or FixedOrientationFeasibilityPolicy()
    ordered_items = sorted(items, key=item_sort_key)
    search = constructive_search(
        ordered_items, containers, tolerance, subset_limit, pack_order_best_fit, selected_policy,
    )

    priority = 1.0 + sum(value.cost for value in containers)
    if search.placements is None:
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
            "candidate_container_ids": [value.container_id for value in search.chosen_containers],
            "n_items": len(items),
            "n_containers": len(containers),
            **selected_policy.metadata(),
        },
    )


solve_level1 = solve
