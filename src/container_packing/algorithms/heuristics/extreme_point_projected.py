"""Các comparator projected-EP Level 1; không thay solver mặc định."""

from __future__ import annotations

from typing import Any

from ...schemas import Container, Item
from ..contracts import AlgorithmOutcome
from .extreme_point_best_fit import solve as solve_best_fit
from .extreme_point_ffd import solve as solve_ffd
from .projected_extreme_points import ProjectedExtremePointProvider


def solve_best_fit_projected(
    items: list[Item], containers: list[Container], settings: dict[str, Any] | None = None,
) -> AlgorithmOutcome:
    return solve_best_fit(
        items, containers, settings,
        candidate_point_provider=ProjectedExtremePointProvider(
            tolerance_mm=float((settings or {}).get("coordinate_tolerance_mm", 1e-6))
        ),
    )


def solve_ffd_projected(
    items: list[Item], containers: list[Container], settings: dict[str, Any] | None = None,
) -> AlgorithmOutcome:
    return solve_ffd(
        items, containers, settings,
        candidate_point_provider=ProjectedExtremePointProvider(
            tolerance_mm=float((settings or {}).get("coordinate_tolerance_mm", 1e-6))
        ),
    )
