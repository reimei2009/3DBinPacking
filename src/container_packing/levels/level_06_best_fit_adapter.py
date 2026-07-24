"""Experimental nesting-aware Extreme-Point Best Fit through the shared adapter."""

from __future__ import annotations

from typing import Any

from ..algorithms.heuristics.extreme_point_best_fit import solve as solve_extreme_point_best_fit
from ..schemas import Container, Item
from .level_06_ffd_adapter import (
    Level06NestingFfdFixtureResult,
    solve_nesting_aware_compound_fixture,
)


def solve_nesting_aware_best_fit_fixture(
    items: list[Item], containers: list[Container], config: dict[str, Any]
) -> Level06NestingFfdFixtureResult:
    """Pack declared nesting compounds with Best Fit and validate independently."""
    return solve_nesting_aware_compound_fixture(
        items,
        containers,
        config,
        constructor=solve_extreme_point_best_fit,
        algorithm_id="extreme_point_best_fit_nesting_fixture",
        adapter_id="level_06_nesting_aware_best_fit_compound_v1",
    )
