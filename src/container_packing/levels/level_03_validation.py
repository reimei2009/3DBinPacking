"""Planned Level 3 validator: horizontal orientation plus Level 2 support.

This module is intentionally not registered as an executable level yet.  It
exists so a future solver can be checked independently before Level 3 is
exposed through the CLI or UI.
"""

from __future__ import annotations

from ..schemas import Container, Item, Placement
from .support_validation import SupportValidation, validate_supported_solution

Level03Validation = SupportValidation


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
) -> Level03Validation:
    """Validate horizontal `XYZ`/`YXZ` placements and exact base support."""
    return validate_supported_solution(
        items,
        containers,
        placements,
        orientation_profile="horizontal_rotatable",
        support_threshold=support_threshold,
        support_epsilon_mm=support_epsilon_mm,
        dense_grid_x=dense_grid_x,
        dense_grid_y=dense_grid_y,
        coordinate_tolerance=coordinate_tolerance,
        weight_tolerance=weight_tolerance,
    )
