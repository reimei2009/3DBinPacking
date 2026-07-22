"""Pure exact support geometry for fixed-orientation rectangular placements."""

from __future__ import annotations

from dataclasses import dataclass

from ..schemas import Placement

Rectangle = tuple[float, float, float, float]


@dataclass(frozen=True)
class SupportGeometry:
    is_on_floor: bool
    supporting_item_ids: tuple[str, ...]
    contact_rectangles: tuple[Rectangle, ...]
    support_area_mm2: float
    base_area_mm2: float
    exact_support_ratio: float
    center_supported: bool


def contact_rectangle(item: Placement, supporter: Placement) -> Rectangle | None:
    x1 = max(item.x_mm, supporter.x_mm)
    y1 = max(item.y_mm, supporter.y_mm)
    x2 = min(item.x_mm + item.length_mm, supporter.x_mm + supporter.length_mm)
    y2 = min(item.y_mm + item.width_mm, supporter.y_mm + supporter.width_mm)
    return None if x2 <= x1 or y2 <= y1 else (x1, y1, x2, y2)


def rectangle_union_area(rectangles: list[Rectangle] | tuple[Rectangle, ...]) -> float:
    """Exact area of the union of axis-aligned rectangles via an x sweep."""
    if not rectangles:
        return 0.0
    xs = sorted({value for rectangle in rectangles for value in (rectangle[0], rectangle[2])})
    area = 0.0
    for left, right in zip(xs, xs[1:]):
        if right <= left:
            continue
        intervals = sorted(
            (y1, y2) for x1, y1, x2, y2 in rectangles if x1 < right and x2 > left
        )
        covered = 0.0
        if intervals:
            start, end = intervals[0]
            for next_start, next_end in intervals[1:]:
                if next_start > end:
                    covered += end - start
                    start, end = next_start, next_end
                else:
                    end = max(end, next_end)
            covered += end - start
        area += (right - left) * covered
    return area


def evaluate_support(
    placement: Placement,
    possible_supporters: list[Placement] | tuple[Placement, ...],
    *,
    epsilon_mm: float,
) -> SupportGeometry:
    """Measure floor/top-face support without applying an acceptance threshold."""
    if epsilon_mm <= 0:
        raise ValueError("epsilon_mm must be positive")
    on_floor = abs(placement.z_mm) <= epsilon_mm
    supporters: list[Placement] = []
    rectangles: list[Rectangle] = []
    if not on_floor:
        for candidate in possible_supporters:
            if candidate.item_id == placement.item_id or candidate.container_id != placement.container_id:
                continue
            if abs(placement.z_mm - (candidate.z_mm + candidate.height_mm)) > epsilon_mm:
                continue
            clipped = contact_rectangle(placement, candidate)
            if clipped is not None:
                supporters.append(candidate)
                rectangles.append(clipped)
    base_area = placement.length_mm * placement.width_mm
    support_area = base_area if on_floor else rectangle_union_area(rectangles)
    exact_ratio = min(1.0, support_area / base_area) if base_area > 0 else 0.0
    center_x = placement.x_mm + placement.length_mm / 2
    center_y = placement.y_mm + placement.width_mm / 2
    center_supported = on_floor or any(
        x1 - epsilon_mm <= center_x <= x2 + epsilon_mm
        and y1 - epsilon_mm <= center_y <= y2 + epsilon_mm
        for x1, y1, x2, y2 in rectangles
    )
    return SupportGeometry(
        is_on_floor=on_floor,
        supporting_item_ids=tuple(sorted(candidate.item_id for candidate in supporters)),
        contact_rectangles=tuple(rectangles),
        support_area_mm2=support_area,
        base_area_mm2=base_area,
        exact_support_ratio=exact_ratio,
        center_supported=center_supported,
    )


def dense_supported_points(
    placement: Placement,
    rectangles: list[Rectangle] | tuple[Rectangle, ...],
    grid_x: int,
    grid_y: int,
    epsilon_mm: float,
) -> int:
    count = 0
    for p in range(grid_x):
        x = placement.x_mm + ((p + 0.5) / grid_x) * placement.length_mm
        for q in range(grid_y):
            y = placement.y_mm + ((q + 0.5) / grid_y) * placement.width_mm
            if any(
                x1 - epsilon_mm <= x <= x2 + epsilon_mm
                and y1 - epsilon_mm <= y <= y2 + epsilon_mm
                for x1, y1, x2, y2 in rectangles
            ):
                count += 1
    return count
