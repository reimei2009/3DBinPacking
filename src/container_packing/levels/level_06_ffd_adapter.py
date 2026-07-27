"""Experimental compound-root Extreme-Point FFD adapter."""

from __future__ import annotations

from typing import Any

from ..algorithms.heuristics.extreme_point_ffd import solve as solve_extreme_point_ffd
from ..schemas import Container, Item
from .level_06_compound_adapter import Level06CompoundAdapter, Level06CompoundResult

# Backward-compatible internal name retained for existing fixture callers.
Level06NestingFfdFixtureResult = Level06CompoundResult


def solve_nesting_aware_ffd_fixture(
    items: list[Item], containers: list[Container], config: dict[str, Any]
) -> Level06CompoundResult:
    return Level06CompoundAdapter(
        "extreme_point_ffd_nesting_fixture",
        "level_06_nesting_aware_ffd_compound_v1",
        solve_extreme_point_ffd,
    ).solve(items, containers, config)
