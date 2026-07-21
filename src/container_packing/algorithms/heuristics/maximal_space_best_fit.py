"""Deterministic fixed-orientation Maximal Empty Spaces Best-Fit heuristic."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scipy.optimize import OptimizeResult

from ..contracts import AlgorithmOutcome
from .constructive_common import candidate_subsets, container_orders, item_sort_key
from .maximal_space_core import (
    EmptySpace,
    MaximalSpaceContainerState,
    MaximalSpaceStats,
    feasible_in_state,
    occupied_bounding_volume,
    place_item,
    space_sort_key,
)
from ...schemas import Container, Item, Placement, SolveResult


@dataclass(frozen=True)
class MaximalSpaceSearchResult:
    placements: list[Placement] | None
    chosen_containers: tuple[Container, ...]
    stats: MaximalSpaceStats


def candidate_score(
    state: MaximalSpaceContainerState,
    item: Item,
    space: EmptySpace,
    container_rank: int,
) -> tuple[float, ...]:
    """Return the objective-aware Best-Fit score for a feasible EMS candidate."""
    is_open = bool(state.placements)
    item_volume = item.length_mm * item.width_mm * item.height_mm
    container_volume = (
        state.container.length_mm * state.container.width_mm * state.container.height_mm
    )
    before = occupied_bounding_volume(state.placements)
    after = occupied_bounding_volume(state.placements, item, space)
    return (
        0.0 if is_open else 1.0,
        0.0 if is_open else float(state.container.cost),
        float(space.volume_mm3 - item_volume),
        float(container_volume - state.loaded_volume_mm3 - item_volume),
        float(state.container.max_weight_kg - state.loaded_weight_kg - item.weight_kg),
        float(after - before),
        float(after),
        float(space.z_mm), float(space.y_mm), float(space.x_mm),
        float(container_rank),
        float(space.length_mm), float(space.width_mm), float(space.height_mm),
    )


def pack_order(
    items: list[Item],
    containers: tuple[Container, ...],
    tolerance: float,
    stats: MaximalSpaceStats,
) -> list[Placement] | None:
    states = [MaximalSpaceContainerState(container) for container in containers]
    stats.maximum_active_spaces = max(stats.maximum_active_spaces, 1 if states else 0)
    for item in items:
        selected: tuple[
            tuple[float, ...], MaximalSpaceContainerState, EmptySpace,
        ] | None = None
        for container_rank, state in enumerate(states):
            for space in sorted(state.empty_spaces, key=space_sort_key):
                stats.empty_spaces_evaluated += 1
                if not feasible_in_state(state, item, space, tolerance):
                    continue
                score = candidate_score(state, item, space, container_rank)
                if selected is None or score < selected[0]:
                    selected = score, state, space
        if selected is None:
            return None
        place_item(selected[1], item, selected[2], stats, tolerance)
    return [placement for state in states for placement in state.placements]


def search_container_subsets(
    ordered_items: list[Item], containers: list[Container], tolerance: float, subset_limit: int,
) -> MaximalSpaceSearchResult:
    stats = MaximalSpaceStats()
    total_weight = sum(value.weight_kg for value in ordered_items)
    total_volume = sum(value.volume_m3 for value in ordered_items)
    for subset in candidate_subsets(containers, subset_limit):
        stats.candidate_subsets_evaluated += 1
        if sum(value.max_weight_kg for value in subset) + tolerance < total_weight:
            continue
        if sum(value.volume_m3 for value in subset) + tolerance < total_volume:
            continue
        for order in container_orders(subset):
            stats.packing_attempts += 1
            placements = pack_order(ordered_items, order, tolerance, stats)
            if placements is not None:
                chosen = tuple({value.container_id: value for value in order}.values())
                return MaximalSpaceSearchResult(placements, chosen, stats)
    return MaximalSpaceSearchResult(None, (), stats)


def solve_level1(
    items: list[Item], containers: list[Container], settings: dict[str, Any] | None = None,
) -> AlgorithmOutcome:
    """Pack all items using EMS Best Fit; FEASIBLE does not prove global optimality."""
    settings = settings or {}
    tolerance = float(settings.get("coordinate_tolerance_mm", 1e-6))
    subset_limit = int(settings.get("subset_enumeration_limit", 12))
    if subset_limit <= 0:
        raise ValueError("subset_enumeration_limit must be positive")
    ordered_items = sorted(items, key=item_sort_key)
    search = search_container_subsets(ordered_items, containers, tolerance, subset_limit)

    priority = 1.0 + sum(value.cost for value in containers)
    if search.placements is None:
        solve = SolveResult(
            status="INFEASIBLE_HEURISTIC",
            message="Maximal-Space heuristic found no complete packing; this is not a proof of infeasibility.",
            objective_value=None, vector=None, raw_result=OptimizeResult(),
        )
    else:
        used_ids = {value.container_id for value in search.placements}
        used_cost = sum(value.cost for value in containers if value.container_id in used_ids)
        objective = len(used_ids) * priority + used_cost
        solve = SolveResult(
            status="FEASIBLE",
            message="Deterministic Maximal Empty Spaces Best Fit found a complete packing.",
            objective_value=float(objective), vector=None, raw_result=OptimizeResult(),
        )
    return AlgorithmOutcome(
        solve=solve,
        placements=[] if search.placements is None else search.placements,
        backend="deterministic/maximal-empty-spaces-best-fit",
        metadata={
            "algorithm_kind": "constructive_heuristic",
            "optimality_proven": False,
            "item_ordering": "decreasing_volume_max_dimension_weight",
            "space_representation": "maximal_empty_spaces_six_way_split",
            "container_selection_strategy": "minimum_count_then_cost_subset_search",
            "candidate_scoring": (
                "open_container_then_incremental_cost_then_space_waste_container_residual_"
                "payload_then_bounding_growth_then_bottom_left_back"
            ),
            "subset_enumeration_limit": subset_limit,
            "candidate_subsets_evaluated": search.stats.candidate_subsets_evaluated,
            "packing_attempts": search.stats.packing_attempts,
            "empty_spaces_evaluated": search.stats.empty_spaces_evaluated,
            "empty_spaces_generated": search.stats.empty_spaces_generated,
            "empty_spaces_pruned": search.stats.empty_spaces_pruned,
            "maximum_active_spaces": search.stats.maximum_active_spaces,
            "candidate_container_ids": [value.container_id for value in search.chosen_containers],
            "n_items": len(items),
            "n_containers": len(containers),
        },
    )
