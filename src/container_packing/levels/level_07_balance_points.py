"""Balance-target candidate origins for generic Level 7 construction."""

from __future__ import annotations

from dataclasses import dataclass

from ..algorithms.heuristics.extreme_point_core import ContainerState, Point
from ..geometry.orientation import OrientedDimensions
from ..schemas import Item
from .load_balance import resolve_container_balance_attributes


@dataclass(frozen=True)
class BalanceAnchorPointProvider:
    """Add feasible COG-target anchors while preserving normal extreme points."""

    balance_config: dict
    policy_id: str = "level_07_balance_anchor_points_v1"

    def points(
        self, state: ContainerState, item: Item, dimensions: OrientedDimensions
    ) -> tuple[Point, ...]:
        del item
        attributes = resolve_container_balance_attributes([state.container], self.balance_config)[
            state.container.container_id
        ]
        target_x = state.container.length_mm * attributes.target_longitudinal_ratio - dimensions.length_mm / 2.0
        target_y = state.container.width_mm * attributes.target_lateral_ratio - dimensions.width_mm / 2.0
        z_values = {point[2] for point in state.extreme_points}
        candidates: set[Point] = set(state.extreme_points)
        for z_mm in z_values:
            candidates.add((target_x, target_y, z_mm))
        for x_mm, y_mm, z_mm in state.extreme_points:
            candidates.add((target_x, y_mm, z_mm))
            candidates.add((x_mm, target_y, z_mm))
        return tuple(sorted(candidates, key=lambda value: (value[2], value[1], value[0])))

    def metadata(self) -> dict[str, object]:
        return {
            "candidate_point_provider": self.policy_id,
            "balance_anchor_mode": "target_center_and_extreme_point_cross_product",
        }
