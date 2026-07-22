"""Level 2 dispatch using shared engines with exact-support feasibility."""

from __future__ import annotations

from typing import Any

from ..algorithms.exact.milp_big_m import solve_level2
from ..algorithms.feasibility import ExactSupportFeasibilityPolicy
from ..algorithms.heuristics.extreme_point_best_fit import solve as solve_extreme_point_best_fit
from ..algorithms.heuristics.extreme_point_ffd import solve as solve_extreme_point_ffd
from ..algorithms.heuristics.extreme_point_hill_climbing import solve as solve_extreme_point_hill_climbing
from ..algorithms.heuristics.maximal_space_best_fit import solve as solve_maximal_space_best_fit
from ..algorithms.metaheuristics.extreme_point_simulated_annealing import solve as solve_extreme_point_simulated_annealing
from ..schemas import Container, Item


def execute_level_02(
    algorithm_id: str, items: list[Item], containers: list[Container], settings: dict[str, Any],
):
    if algorithm_id == "milp_big_m":
        return solve_level2(items, containers, settings)
    executors = {
        "extreme_point_best_fit": solve_extreme_point_best_fit,
        "extreme_point_ffd": solve_extreme_point_ffd,
        "extreme_point_hill_climbing": solve_extreme_point_hill_climbing,
        "extreme_point_simulated_annealing": solve_extreme_point_simulated_annealing,
        "maximal_space_best_fit": solve_maximal_space_best_fit,
    }
    try:
        executor = executors[algorithm_id]
    except KeyError as exc:
        available = ", ".join([*sorted(executors), "milp_big_m"])
        raise ValueError(f"Level 2 algorithm {algorithm_id!r} is not implemented. Available: {available}") from exc
    support = settings.get("support", {})
    policy = ExactSupportFeasibilityPolicy(
        threshold=float(support.get("threshold", 0.8)),
        epsilon_mm=float(support.get("epsilon_mm", 1e-4)),
    )
    return executor(items, containers, settings, policy=policy)
