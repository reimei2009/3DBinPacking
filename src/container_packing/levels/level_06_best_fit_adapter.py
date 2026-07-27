"""Experimental nesting-aware Extreme-Point Best Fit through the shared adapter."""

from __future__ import annotations

from typing import Any

from ..algorithms.heuristics.extreme_point_best_fit import solve as solve_extreme_point_best_fit
from ..schemas import Container, Item
from .level_06_compound_adapter import Level06CompoundAdapter, Level06CompoundResult


def solve_nesting_aware_best_fit_fixture(
    items: list[Item], containers: list[Container], config: dict[str, Any]
) -> Level06CompoundResult:
    """Pack declared nesting compounds with Best Fit and validate independently."""
    return Level06CompoundAdapter(
        "extreme_point_best_fit_nesting_fixture",
        "level_06_nesting_aware_best_fit_compound_v1",
        solve_extreme_point_best_fit,
    ).solve(items, containers, config)
