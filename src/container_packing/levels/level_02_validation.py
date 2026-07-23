"""Level 2 adapter for shared exact geometric support validation."""

from __future__ import annotations

from ..geometry.support import rectangle_union_area
from ..schemas import Container, Item, Placement
from .support_validation import SupportRecord, SupportValidation, validate_supported_solution

Level02Validation = SupportValidation


def validate_solution(
    items: list[Item],
    containers: list[Container],
    placements: list[Placement],
    *,
    support_threshold: float = 0.8,
    support_epsilon_mm: float = 1e-4,
    dense_grid_x: int = 16,
    dense_grid_y: int = 16,
    coordinate_tolerance: float = 1e-4,
    weight_tolerance: float = 1e-6,
) -> Level02Validation:
    """Validate the fixed-orientation, base-support Level 2 contract."""
    return validate_supported_solution(
        items,
        containers,
        placements,
        orientation_profile="fixed",
        support_threshold=support_threshold,
        support_epsilon_mm=support_epsilon_mm,
        dense_grid_x=dense_grid_x,
        dense_grid_y=dense_grid_y,
        coordinate_tolerance=coordinate_tolerance,
        weight_tolerance=weight_tolerance,
    )


__all__ = ["Level02Validation", "SupportRecord", "rectangle_union_area", "validate_solution"]
