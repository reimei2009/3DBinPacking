"""Single dispatch table for Level 1 algorithm implementations."""

from __future__ import annotations

from typing import Any, Callable

from ..algorithms.contracts import AlgorithmOutcome
from ..algorithms.exact.milp_big_m import solve_level1 as solve_milp_big_m
from ..algorithms.heuristics.extreme_point_ffd import solve_level1 as solve_extreme_point_ffd
from ..algorithms.heuristics.extreme_point_hill_climbing import solve_level1 as solve_extreme_point_hill_climbing
from ..algorithms.metaheuristics.extreme_point_simulated_annealing import solve_level1 as solve_extreme_point_simulated_annealing
from ..schemas import Container, Item

Level01Executor = Callable[[list[Item], list[Container], dict[str, Any] | None], AlgorithmOutcome]

LEVEL_01_EXECUTORS: dict[str, Level01Executor] = {
    "extreme_point_ffd": solve_extreme_point_ffd,
    "extreme_point_hill_climbing": solve_extreme_point_hill_climbing,
    "extreme_point_simulated_annealing": solve_extreme_point_simulated_annealing,
    "milp_big_m": solve_milp_big_m,
}


def execute_level_01(
    algorithm_id: str, items: list[Item], containers: list[Container], settings: dict[str, Any],
) -> AlgorithmOutcome:
    try:
        executor = LEVEL_01_EXECUTORS[algorithm_id]
    except KeyError as exc:
        available = ", ".join(sorted(LEVEL_01_EXECUTORS))
        raise ValueError(f"Level 1 algorithm {algorithm_id!r} is not implemented. Available: {available}") from exc
    return executor(items, containers, settings)
