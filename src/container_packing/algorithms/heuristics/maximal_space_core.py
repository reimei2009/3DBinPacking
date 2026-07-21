"""Geometry core for fixed-orientation Maximal Empty Spaces packing."""

from __future__ import annotations

from dataclasses import dataclass, field

from ...schemas import Container, Item, Placement


@dataclass(frozen=True)
class EmptySpace:
    x_mm: float
    y_mm: float
    z_mm: float
    length_mm: float
    width_mm: float
    height_mm: float

    @property
    def max_x_mm(self) -> float:
        return self.x_mm + self.length_mm

    @property
    def max_y_mm(self) -> float:
        return self.y_mm + self.width_mm

    @property
    def max_z_mm(self) -> float:
        return self.z_mm + self.height_mm

    @property
    def volume_mm3(self) -> float:
        return self.length_mm * self.width_mm * self.height_mm


@dataclass
class MaximalSpaceStats:
    candidate_subsets_evaluated: int = 0
    packing_attempts: int = 0
    empty_spaces_evaluated: int = 0
    empty_spaces_generated: int = 0
    empty_spaces_pruned: int = 0
    maximum_active_spaces: int = 0


@dataclass
class MaximalSpaceContainerState:
    container: Container
    placements: list[Placement] = field(default_factory=list)
    empty_spaces: list[EmptySpace] = field(default_factory=list)
    loaded_weight_kg: float = 0.0
    loaded_volume_mm3: float = 0.0

    def __post_init__(self) -> None:
        if not self.empty_spaces:
            self.empty_spaces = [EmptySpace(
                0.0, 0.0, 0.0,
                self.container.length_mm, self.container.width_mm, self.container.height_mm,
            )]


def spaces_intersect_box(space: EmptySpace, box: Placement, tolerance: float = 1e-6) -> bool:
    return not (
        space.max_x_mm <= box.x_mm + tolerance
        or box.x_mm + box.length_mm <= space.x_mm + tolerance
        or space.max_y_mm <= box.y_mm + tolerance
        or box.y_mm + box.width_mm <= space.y_mm + tolerance
        or space.max_z_mm <= box.z_mm + tolerance
        or box.z_mm + box.height_mm <= space.z_mm + tolerance
    )


def _positive_space(
    x: float, y: float, z: float, length: float, width: float, height: float, tolerance: float,
) -> EmptySpace | None:
    if length <= tolerance or width <= tolerance or height <= tolerance:
        return None
    return EmptySpace(x, y, z, length, width, height)


def subtract_placement(
    space: EmptySpace, placement: Placement, tolerance: float = 1e-6,
) -> list[EmptySpace]:
    """Return up to six empty slabs covering ``space`` minus an intersecting box."""
    if not spaces_intersect_box(space, placement, tolerance):
        return [space]
    ix0 = max(space.x_mm, placement.x_mm)
    iy0 = max(space.y_mm, placement.y_mm)
    iz0 = max(space.z_mm, placement.z_mm)
    ix1 = min(space.max_x_mm, placement.x_mm + placement.length_mm)
    iy1 = min(space.max_y_mm, placement.y_mm + placement.width_mm)
    iz1 = min(space.max_z_mm, placement.z_mm + placement.height_mm)
    candidates = (
        _positive_space(
            space.x_mm, space.y_mm, space.z_mm,
            ix0 - space.x_mm, space.width_mm, space.height_mm, tolerance,
        ),
        _positive_space(
            ix1, space.y_mm, space.z_mm,
            space.max_x_mm - ix1, space.width_mm, space.height_mm, tolerance,
        ),
        _positive_space(
            space.x_mm, space.y_mm, space.z_mm,
            space.length_mm, iy0 - space.y_mm, space.height_mm, tolerance,
        ),
        _positive_space(
            space.x_mm, iy1, space.z_mm,
            space.length_mm, space.max_y_mm - iy1, space.height_mm, tolerance,
        ),
        _positive_space(
            space.x_mm, space.y_mm, space.z_mm,
            space.length_mm, space.width_mm, iz0 - space.z_mm, tolerance,
        ),
        _positive_space(
            space.x_mm, space.y_mm, iz1,
            space.length_mm, space.width_mm, space.max_z_mm - iz1, tolerance,
        ),
    )
    return [value for value in candidates if value is not None]


def contains_space(outer: EmptySpace, inner: EmptySpace, tolerance: float = 1e-6) -> bool:
    return (
        inner.x_mm >= outer.x_mm - tolerance
        and inner.y_mm >= outer.y_mm - tolerance
        and inner.z_mm >= outer.z_mm - tolerance
        and inner.max_x_mm <= outer.max_x_mm + tolerance
        and inner.max_y_mm <= outer.max_y_mm + tolerance
        and inner.max_z_mm <= outer.max_z_mm + tolerance
    )


def space_sort_key(space: EmptySpace) -> tuple[float, ...]:
    return (
        space.z_mm, space.y_mm, space.x_mm, space.volume_mm3,
        space.length_mm, space.width_mm, space.height_mm,
    )


def prune_maximal_spaces(
    spaces: list[EmptySpace], tolerance: float = 1e-6,
) -> list[EmptySpace]:
    """Remove duplicates, degenerate spaces, and spaces contained by larger ones."""
    unique = {
        value for value in spaces
        if value.length_mm > tolerance and value.width_mm > tolerance and value.height_mm > tolerance
    }
    by_size = sorted(unique, key=lambda value: (-value.volume_mm3, *space_sort_key(value)))
    maximal: list[EmptySpace] = []
    for candidate in by_size:
        if any(contains_space(existing, candidate, tolerance) for existing in maximal):
            continue
        maximal = [
            existing for existing in maximal
            if not contains_space(candidate, existing, tolerance)
        ]
        maximal.append(candidate)
    return sorted(maximal, key=space_sort_key)


def update_maximal_spaces(
    spaces: list[EmptySpace], placement: Placement, tolerance: float = 1e-6,
) -> tuple[list[EmptySpace], int, int]:
    raw: list[EmptySpace] = []
    generated = 0
    for space in spaces:
        intersects = spaces_intersect_box(space, placement, tolerance)
        residual = subtract_placement(space, placement, tolerance)
        raw.extend(residual)
        if intersects:
            generated += len(residual)
    maximal = prune_maximal_spaces(raw, tolerance)
    return maximal, generated, len(raw) - len(maximal)


def item_fits_space(item: Item, space: EmptySpace, tolerance: float = 1e-6) -> bool:
    return (
        item.length_mm <= space.length_mm + tolerance
        and item.width_mm <= space.width_mm + tolerance
        and item.height_mm <= space.height_mm + tolerance
    )


def item_overlaps_placement(
    item: Item, space: EmptySpace, placed: Placement, tolerance: float = 1e-6,
) -> bool:
    return not (
        space.x_mm + item.length_mm <= placed.x_mm + tolerance
        or placed.x_mm + placed.length_mm <= space.x_mm + tolerance
        or space.y_mm + item.width_mm <= placed.y_mm + tolerance
        or placed.y_mm + placed.width_mm <= space.y_mm + tolerance
        or space.z_mm + item.height_mm <= placed.z_mm + tolerance
        or placed.z_mm + placed.height_mm <= space.z_mm + tolerance
    )


def feasible_in_state(
    state: MaximalSpaceContainerState, item: Item, space: EmptySpace, tolerance: float = 1e-6,
) -> bool:
    if not item_fits_space(item, space, tolerance):
        return False
    if state.loaded_weight_kg + item.weight_kg > state.container.max_weight_kg + tolerance:
        return False
    return not any(
        item_overlaps_placement(item, space, placed, tolerance)
        for placed in state.placements
    )


def place_item(
    state: MaximalSpaceContainerState, item: Item, space: EmptySpace,
    stats: MaximalSpaceStats, tolerance: float = 1e-6,
) -> Placement:
    placement = Placement(
        item_id=item.item_id, container_id=state.container.container_id,
        x_mm=space.x_mm, y_mm=space.y_mm, z_mm=space.z_mm,
        length_mm=item.length_mm, width_mm=item.width_mm, height_mm=item.height_mm,
        weight_kg=item.weight_kg,
    )
    state.placements.append(placement)
    state.loaded_weight_kg += item.weight_kg
    state.loaded_volume_mm3 += item.length_mm * item.width_mm * item.height_mm
    state.empty_spaces, generated, pruned = update_maximal_spaces(
        state.empty_spaces, placement, tolerance,
    )
    stats.empty_spaces_generated += generated
    stats.empty_spaces_pruned += pruned
    stats.maximum_active_spaces = max(stats.maximum_active_spaces, len(state.empty_spaces))
    return placement


def occupied_bounding_volume(
    placements: list[Placement], item: Item | None = None, space: EmptySpace | None = None,
) -> float:
    if not placements and item is None:
        return 0.0
    max_x = max((value.x_mm + value.length_mm for value in placements), default=0.0)
    max_y = max((value.y_mm + value.width_mm for value in placements), default=0.0)
    max_z = max((value.z_mm + value.height_mm for value in placements), default=0.0)
    if item is not None and space is not None:
        max_x = max(max_x, space.x_mm + item.length_mm)
        max_y = max(max_y, space.y_mm + item.width_mm)
        max_z = max(max_z, space.z_mm + item.height_mm)
    return max_x * max_y * max_z
