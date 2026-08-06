"""Bounded EP-anchored look-ahead guidance for the Level 1 FFD comparator.

The detector is deliberately advisory: ray clearances rank points but never
replace the exact placement-feasibility policy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import TYPE_CHECKING

from ...schemas import Placement

if TYPE_CHECKING:
    from .extreme_point_core import ContainerState


@dataclass(frozen=True)
class GapFillSettings:
    lookahead_window_size: int = 5
    max_constrained_points_per_step: int = 8
    max_candidates_per_step: int = 64
    maximum_reorder_distance: int = 4

    @classmethod
    def from_mapping(cls, value: object) -> "GapFillSettings":
        raw = {} if value is None else value
        if not isinstance(raw, dict):
            raise ValueError("gap_fill must be a mapping")
        result = cls(**{key: raw.get(key, getattr(cls(), key)) for key in (
            "lookahead_window_size", "max_constrained_points_per_step",
            "max_candidates_per_step", "maximum_reorder_distance",
        )})
        if result.lookahead_window_size < 2:
            raise ValueError("gap_fill.lookahead_window_size must be at least 2")
        if min(result.max_constrained_points_per_step, result.max_candidates_per_step,
               result.maximum_reorder_distance) <= 0:
            raise ValueError("gap_fill limits must be positive")
        return result

    def metadata(self) -> dict[str, object]:
        return {
            "gap_fill_policy": "ep_anchored_bounded_lookahead_v1",
            "gap_detector": "positive_ray_clearance_advisory_v1",
            "gap_fill_lookahead_window_size": self.lookahead_window_size,
            "gap_fill_max_constrained_points_per_step": self.max_constrained_points_per_step,
            "gap_fill_max_candidates_per_step": self.max_candidates_per_step,
            "gap_fill_maximum_reorder_distance": self.maximum_reorder_distance,
        }


@dataclass(frozen=True)
class ConstrainedPoint:
    state_index: int
    point: tuple[float, float, float]
    clearance_mm: tuple[float, float, float]
    rank_key: tuple[float, ...]


@dataclass
class GapFillStatistics:
    constrained_points_detected: int = 0
    constrained_points_considered: int = 0
    candidates_evaluated: int = 0
    candidates_feasible: int = 0
    insertions: int = 0
    max_reorder_distance: int = 0
    realized_item_order: list[str] = field(default_factory=list)

    def metadata(self) -> dict[str, object]:
        return {
            "gap_fill_constrained_points_detected": self.constrained_points_detected,
            "gap_fill_constrained_points_considered": self.constrained_points_considered,
            "gap_fill_candidates_evaluated": self.candidates_evaluated,
            "gap_fill_candidates_feasible": self.candidates_feasible,
            "gap_fill_insertions": self.insertions,
            "gap_fill_max_realized_reorder_distance": self.max_reorder_distance,
            "gap_fill_realized_item_order": self.realized_item_order,
        }


def rank_constrained_points(states: list["ContainerState"]) -> tuple[ConstrainedPoint, ...]:
    """Rank only already-open containers; values are advisory, never a cuboid."""
    values: list[ConstrainedPoint] = []
    for state_index, state in enumerate(states):
        if not state.placements:
            continue
        container = state.container
        for point in state.extreme_points:
            x, y, z = point
            clearances = _ray_clearances(state.placements, container.length_mm, container.width_mm, container.height_mm, point)
            normalized = (
                clearances[0] / container.length_mm + clearances[1] / container.width_mm
                + clearances[2] / container.height_mm
            )
            blocked = sum(value < bound - 1e-9 for value, bound in zip(
                clearances, (container.length_mm - x, container.width_mm - y, container.height_mm - z)
            ))
            values.append(ConstrainedPoint(
                state_index, point, clearances,
                (-float(blocked), normalized, -z / container.height_mm, z, y, x),
            ))
    return tuple(sorted(values, key=lambda value: value.rank_key))


def _ray_clearances(placements: list[Placement], length: float, width: float, height: float,
                    point: tuple[float, float, float]) -> tuple[float, float, float]:
    x, y, z = point
    dx, dy, dz = length - x, width - y, height - z
    for placed in placements:
        if placed.y_mm <= y <= placed.y_mm + placed.width_mm and placed.z_mm <= z <= placed.z_mm + placed.height_mm and placed.x_mm >= x:
            dx = min(dx, placed.x_mm - x)
        if placed.x_mm <= x <= placed.x_mm + placed.length_mm and placed.z_mm <= z <= placed.z_mm + placed.height_mm and placed.y_mm >= y:
            dy = min(dy, placed.y_mm - y)
        if placed.x_mm <= x <= placed.x_mm + placed.length_mm and placed.y_mm <= y <= placed.y_mm + placed.width_mm and placed.z_mm >= z:
            dz = min(dz, placed.z_mm - z)
    return (max(0.0, dx), max(0.0, dy), max(0.0, dz))
