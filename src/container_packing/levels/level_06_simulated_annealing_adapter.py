"""Compound-aware Simulated Annealing adapter with fixed nesting relations."""

from __future__ import annotations

from typing import Any

from ..algorithms.metaheuristics.extreme_point_simulated_annealing import solve as solve_simulated_annealing
from ..schemas import Container, Item
from .level_06_compound_adapter import Level06CompoundAdapter, Level06CompoundResult


def solve_nesting_aware_simulated_annealing_fixture(
    items: list[Item], containers: list[Container], config: dict[str, Any]
) -> Level06CompoundResult:
    return Level06CompoundAdapter(
        "extreme_point_simulated_annealing_nesting_fixture",
        "level_06_nesting_aware_simulated_annealing_compound_v1",
        solve_simulated_annealing,
    ).solve(items, containers, config)
