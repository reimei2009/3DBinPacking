"""Shared fixed-orientation Extreme-Point construction primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..feasibility import FixedOrientationFeasibilityPolicy, PlacementFeasibilityPolicy
from ..orientation import OrientationProvider, fixed_orientation_provider
from ...geometry.orientation import OrientedDimensions
from ...schemas import Container, Item, Placement
from .constructive_common import candidate_subsets, container_orders, item_sort_key

Point = tuple[float, float, float]
PackOrder = Callable[
    [list[Item], tuple[Container, ...], float, "SearchStats", PlacementFeasibilityPolicy],
    list[Placement] | None,
]


@dataclass
class ContainerState:
    container: Container
    placements: list[Placement] = field(default_factory=list)
    extreme_points: set[Point] = field(default_factory=lambda: {(0.0, 0.0, 0.0)})
    loaded_weight_kg: float = 0.0

    @property
    def loaded_volume_mm3(self) -> float:
        return sum(
            value.length_mm * value.width_mm * value.height_mm
            for value in self.placements
        )


@dataclass
class SearchStats:
    candidate_subsets_evaluated: int = 0
    packing_attempts: int = 0
    extreme_points_evaluated: int = 0
    orientation_candidates_evaluated: int = 0


@dataclass(frozen=True)
class ConstructiveSearchResult:
    placements: list[Placement] | None
    chosen_containers: tuple[Container, ...]
    stats: SearchStats


def candidate_placement(
    state: ContainerState,
    item: Item,
    point: Point,
    dimensions: OrientedDimensions | None = None,
) -> Placement:
    x, y, z = point
    selected_dimensions = dimensions or fixed_orientation_provider().candidates(item)[0]
    return Placement(
        item_id=item.item_id, container_id=state.container.container_id,
        x_mm=x, y_mm=y, z_mm=z,
        length_mm=selected_dimensions.length_mm,
        width_mm=selected_dimensions.width_mm,
        height_mm=selected_dimensions.height_mm,
        weight_kg=item.weight_kg,
        orientation_code=selected_dimensions.code,
    )


def fits(
    state: ContainerState,
    item: Item,
    point: Point,
    tolerance: float,
    policy: PlacementFeasibilityPolicy | None = None,
    dimensions: OrientedDimensions | None = None,
) -> bool:
    selected_policy = policy or FixedOrientationFeasibilityPolicy()
    return selected_policy.allows(
        state.container,
        state.placements,
        candidate_placement(state, item, point, dimensions),
        loaded_weight_kg=state.loaded_weight_kg,
        tolerance=tolerance,
    )


def _point_inside_box(point: Point, box: Placement, tolerance: float) -> bool:
    x, y, z = point
    return (
        box.x_mm - tolerance <= x < box.x_mm + box.length_mm - tolerance
        and box.y_mm - tolerance <= y < box.y_mm + box.width_mm - tolerance
        and box.z_mm - tolerance <= z < box.z_mm + box.height_mm - tolerance
    )


def update_extreme_points(state: ContainerState, placement: Placement, tolerance: float) -> None:
    state.extreme_points.update({
        (placement.x_mm + placement.length_mm, placement.y_mm, placement.z_mm),
        (placement.x_mm, placement.y_mm + placement.width_mm, placement.z_mm),
        (placement.x_mm, placement.y_mm, placement.z_mm + placement.height_mm),
    })
    container = state.container
    state.extreme_points = {
        point for point in state.extreme_points
        if point[0] <= container.length_mm + tolerance
        and point[1] <= container.width_mm + tolerance
        and point[2] <= container.height_mm + tolerance
        and not any(_point_inside_box(point, box, tolerance) for box in state.placements)
    }


def place_item(state: ContainerState, item: Item, point: Point, tolerance: float) -> Placement:
    placement = candidate_placement(state, item, point)
    return place_candidate(state, placement, tolerance)


def place_candidate(state: ContainerState, placement: Placement, tolerance: float) -> Placement:
    """Commit an already feasibility-checked candidate to its container state."""
    state.placements.append(placement)
    state.loaded_weight_kg += placement.weight_kg
    update_extreme_points(state, placement, tolerance)
    return placement


def pack_order_first_fit(
    items: list[Item], containers: tuple[Container, ...], tolerance: float, stats: SearchStats,
    policy: PlacementFeasibilityPolicy, *, orientation_provider: OrientationProvider | None = None,
) -> list[Placement] | None:
    """Place the first feasible extreme-point/orientation candidate in order."""
    selected_provider = orientation_provider or fixed_orientation_provider()
    states = [ContainerState(container) for container in containers]
    for item in items:
        selected: tuple[ContainerState, Placement] | None = None
        for state in states:
            for point in sorted(state.extreme_points, key=lambda value: (value[2], value[1], value[0])):
                stats.extreme_points_evaluated += 1
                for dimensions in selected_provider.candidates(item):
                    stats.orientation_candidates_evaluated += 1
                    candidate = candidate_placement(state, item, point, dimensions)
                    if selected_policy_allows(state, candidate, tolerance, policy):
                        selected = state, candidate
                        break
                if selected is not None:
                    break
            if selected is not None:
                break
        if selected is None:
            return None
        place_candidate(selected[0], selected[1], tolerance)
    return [placement for state in states for placement in state.placements]


def selected_policy_allows(
    state: ContainerState,
    candidate: Placement,
    tolerance: float,
    policy: PlacementFeasibilityPolicy,
) -> bool:
    """Evaluate a concrete candidate so its orientation reaches the policy."""
    return policy.allows(
        state.container,
        state.placements,
        candidate,
        loaded_weight_kg=state.loaded_weight_kg,
        tolerance=tolerance,
    )


def constructive_search(
    ordered_items: list[Item], containers: list[Container], tolerance: float,
    subset_limit: int, pack_order: PackOrder, policy: PlacementFeasibilityPolicy,
) -> ConstructiveSearchResult:
    total_weight = sum(value.weight_kg for value in ordered_items)
    total_volume = sum(value.volume_m3 for value in ordered_items)
    stats = SearchStats()
    for subset in candidate_subsets(containers, subset_limit):
        stats.candidate_subsets_evaluated += 1
        if sum(value.max_weight_kg for value in subset) + tolerance < total_weight:
            continue
        if sum(value.volume_m3 for value in subset) + tolerance < total_volume:
            continue
        for container_order in container_orders(subset):
            stats.packing_attempts += 1
            placements = pack_order(ordered_items, container_order, tolerance, stats, policy)
            if placements is not None:
                chosen = tuple({value.container_id: value for value in container_order}.values())
                return ConstructiveSearchResult(placements, chosen, stats)
    return ConstructiveSearchResult(None, (), stats)
