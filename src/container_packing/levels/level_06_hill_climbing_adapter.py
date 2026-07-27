"""Compound-aware Hill Climbing adapter with fixed nesting relations."""

from __future__ import annotations

from typing import Any

from ..algorithms.heuristics.extreme_point_hill_climbing import solve as solve_hill_climbing
from ..schemas import Container, Item
from .level_06_compound_adapter import Level06CompoundAdapter, Level06CompoundResult


def solve_nesting_aware_hill_climbing_fixture(
    items: list[Item], containers: list[Container], config: dict[str, Any]
) -> Level06CompoundResult:
    return Level06CompoundAdapter(
        "extreme_point_hill_climbing_nesting_fixture",
        "level_06_nesting_aware_hill_climbing_compound_v1",
        solve_hill_climbing,
    ).solve(items, containers, config)
