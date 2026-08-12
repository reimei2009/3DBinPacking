"""Projected Extreme-Point provider dùng cho comparator nghiên cứu Level 1."""

from __future__ import annotations

from dataclasses import dataclass

from ...geometry.orientation import OrientedDimensions
from ...schemas import Item, Placement
from .candidate_points import Point


@dataclass
class ProjectedExtremePointProvider:
    """Mở rộng ba EP kề bằng các projection âm theo từng trục.

    Provider chỉ sinh/rank điểm. Mọi placement vẫn phải đi qua feasibility
    policy của constructor; vì vậy projection không được xem là free-space exact.
    """

    tolerance_mm: float = 1e-6
    points_generated: int = 0
    duplicate_points_pruned: int = 0
    dominated_points_pruned: int = 0

    def points(self, state, item: Item, dimensions: OrientedDimensions) -> tuple[Point, ...]:
        del item
        canonical = set(state.extreme_points)
        projected = set(canonical)
        for point in tuple(canonical):
            projected.update(self._axis_projections(point, state.placements))
        bounded = [
            point for point in projected
            if point[0] + dimensions.length_mm <= state.container.length_mm + self.tolerance_mm
            and point[1] + dimensions.width_mm <= state.container.width_mm + self.tolerance_mm
            and point[2] + dimensions.height_mm <= state.container.height_mm + self.tolerance_mm
            and not any(self._inside(point, box) for box in state.placements)
        ]
        self.points_generated += len(projected)
        deduplicated = self._deduplicate(bounded)
        self.duplicate_points_pruned += len(bounded) - len(deduplicated)
        retained = self._prune_dominated(deduplicated, state.placements, dimensions)
        self.dominated_points_pruned += len(deduplicated) - len(retained)
        return tuple(sorted(retained, key=lambda value: (value[2], value[1], value[0])))

    def _axis_projections(
        self, point: Point, placements: list[Placement],
    ) -> set[Point]:
        x, y, z = point
        xs = {0.0}
        ys = {0.0}
        zs = {0.0}
        for box in placements:
            if self._within(y, box.y_mm, box.y_mm + box.width_mm) and self._within(
                z, box.z_mm, box.z_mm + box.height_mm
            ):
                edge = box.x_mm + box.length_mm
                if edge <= x + self.tolerance_mm:
                    xs.add(edge)
            if self._within(x, box.x_mm, box.x_mm + box.length_mm) and self._within(
                z, box.z_mm, box.z_mm + box.height_mm
            ):
                edge = box.y_mm + box.width_mm
                if edge <= y + self.tolerance_mm:
                    ys.add(edge)
            if self._within(x, box.x_mm, box.x_mm + box.length_mm) and self._within(
                y, box.y_mm, box.y_mm + box.width_mm
            ):
                edge = box.z_mm + box.height_mm
                if edge <= z + self.tolerance_mm:
                    zs.add(edge)
        return ({(value, y, z) for value in xs}
                | {(x, value, z) for value in ys}
                | {(x, y, value) for value in zs})

    def _deduplicate(self, points: list[Point]) -> list[Point]:
        scale = max(self.tolerance_mm, 1e-12)
        unique: dict[tuple[int, int, int], Point] = {}
        for point in sorted(points, key=lambda value: (value[2], value[1], value[0])):
            key = tuple(round(value / scale) for value in point)
            unique.setdefault(key, point)
        return list(unique.values())

    def _prune_dominated(
        self,
        points: list[Point],
        placements: list[Placement],
        dimensions: OrientedDimensions,
    ) -> list[Point]:
        retained: list[Point] = []
        for point in sorted(points, key=lambda value: (sum(value), value[2], value[1], value[0])):
            if any(
                all(left <= right + self.tolerance_mm for left, right in zip(other, point))
                and self._swept_region_clear(other, point, dimensions, placements)
                for other in retained
            ):
                continue
            retained.append(point)
        return retained

    def _swept_region_clear(
        self,
        lower: Point,
        upper: Point,
        dimensions: OrientedDimensions,
        placements: list[Placement],
    ) -> bool:
        x0, y0, z0 = lower
        x1 = upper[0] + dimensions.length_mm
        y1 = upper[1] + dimensions.width_mm
        z1 = upper[2] + dimensions.height_mm
        return not any(
            x0 < box.x_mm + box.length_mm - self.tolerance_mm
            and x1 > box.x_mm + self.tolerance_mm
            and y0 < box.y_mm + box.width_mm - self.tolerance_mm
            and y1 > box.y_mm + self.tolerance_mm
            and z0 < box.z_mm + box.height_mm - self.tolerance_mm
            and z1 > box.z_mm + self.tolerance_mm
            for box in placements
        )

    def _inside(self, point: Point, box: Placement) -> bool:
        return (
            box.x_mm - self.tolerance_mm <= point[0] < box.x_mm + box.length_mm - self.tolerance_mm
            and box.y_mm - self.tolerance_mm <= point[1] < box.y_mm + box.width_mm - self.tolerance_mm
            and box.z_mm - self.tolerance_mm <= point[2] < box.z_mm + box.height_mm - self.tolerance_mm
        )

    def _within(self, value: float, lower: float, upper: float) -> bool:
        return lower - self.tolerance_mm <= value <= upper + self.tolerance_mm

    def metadata(self) -> dict[str, object]:
        return {
            "candidate_point_provider": "projected_extreme_points_v1",
            "projected_ep_model": "adjacent_plus_negative_axis_projection",
            "projected_ep_points_generated": self.points_generated,
            "projected_ep_duplicate_points_pruned": self.duplicate_points_pruned,
            "projected_ep_dominated_points_pruned": self.dominated_points_pruned,
            "projected_ep_tolerance_mm": self.tolerance_mm,
        }
