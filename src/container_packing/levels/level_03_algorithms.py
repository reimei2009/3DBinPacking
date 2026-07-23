"""Level 3 dispatch: horizontal orientation with exact geometric support."""

from __future__ import annotations

from typing import Any

from ..algorithms.feasibility import ExactSupportFeasibilityPolicy
from ..algorithms.exact.milp_big_m import solve_level3
from ..algorithms.heuristics.extreme_point_best_fit import solve as solve_extreme_point_best_fit
from ..algorithms.heuristics.extreme_point_ffd import solve as solve_extreme_point_ffd
from ..algorithms.heuristics.extreme_point_hill_climbing import solve as solve_extreme_point_hill_climbing
from ..algorithms.heuristics.maximal_space_best_fit import solve as solve_maximal_space_best_fit
from ..algorithms.metaheuristics.extreme_point_simulated_annealing import solve as solve_extreme_point_simulated_annealing
from ..algorithms.orientation import horizontal_orientation_provider
from ..schemas import Container, Item


def execute_level_03(
    algorithm_id: str, items: list[Item], containers: list[Container], settings: dict[str, Any]
):
    if algorithm_id == "milp_big_m":
        max_items = int(settings.get("orientation_reference_max_items", 5))
        if len(items) > max_items:
            raise ValueError(
                f"Level 3 MILP Big-M is an exact reference limited to {max_items} items; "
                f"received {len(items)}. Use extreme_point_ffd for practical runs."
            )
        return solve_level3(items, containers, settings)
    executors = {
        "extreme_point_ffd": solve_extreme_point_ffd,
        "extreme_point_best_fit": solve_extreme_point_best_fit,
        "extreme_point_hill_climbing": solve_extreme_point_hill_climbing,
        "extreme_point_simulated_annealing": solve_extreme_point_simulated_annealing,
        "maximal_space_best_fit": solve_maximal_space_best_fit,
    }
    try:
        executor = executors[algorithm_id]
    except KeyError as exc:
        raise ValueError(
            "Level 3 implements MILP Big-M reference, Extreme Point FFD/Best Fit, Hill Climbing, Simulated "
            "Annealing, and Maximal Empty Spaces."
        ) from exc
    support = settings.get("support", {})
    policy = ExactSupportFeasibilityPolicy(
        threshold=float(support.get("threshold", 0.8)),
        epsilon_mm=float(support.get("epsilon_mm", 1e-4)),
        policy_id="horizontal_orientation_geometry_payload_exact_support",
    )
    return executor(
        items,
        containers,
        settings,
        policy=policy,
        orientation_provider=horizontal_orientation_provider(),
    )
