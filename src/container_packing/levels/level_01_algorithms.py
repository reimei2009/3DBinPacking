"""Single dispatch table for Level 1 algorithm implementations."""

from __future__ import annotations

from typing import Any, Callable

from ..algorithms.contracts import AlgorithmOutcome
from ..algorithms.search import (
    InventoryLevelAdapter,
)
from ..algorithms.orientation import fixed_orientation_provider
from ..algorithms.exact.milp_big_m import solve_level1 as solve_milp_big_m
from ..algorithms.heuristics.extreme_point_best_fit import solve as solve_extreme_point_best_fit
from ..algorithms.heuristics.extreme_point_ffd import solve as solve_extreme_point_ffd
from ..algorithms.heuristics.extreme_point_ffd_gap_fill import solve as solve_extreme_point_ffd_gap_fill
from ..algorithms.heuristics.extreme_point_projected import (
    solve_best_fit_projected,
    solve_ffd_projected,
)
from ..algorithms.heuristics.extreme_point_hill_climbing import solve as solve_extreme_point_hill_climbing
from ..algorithms.heuristics.maximal_space_best_fit import solve as solve_maximal_space_best_fit
from ..algorithms.metaheuristics.extreme_point_simulated_annealing import solve as solve_extreme_point_simulated_annealing
from ..schemas import Container, Item
from .level_01_validation import validate_solution

Level01Executor = Callable[[list[Item], list[Container], dict[str, Any] | None], AlgorithmOutcome]

LEVEL_01_EXECUTORS: dict[str, Level01Executor] = {
    "extreme_point_best_fit": solve_extreme_point_best_fit,
    "extreme_point_ffd": solve_extreme_point_ffd,
    "extreme_point_ffd_gap_fill": solve_extreme_point_ffd_gap_fill,
    "extreme_point_best_fit_projected_ep": solve_best_fit_projected,
    "extreme_point_ffd_projected_ep": solve_ffd_projected,
    "extreme_point_hill_climbing": solve_extreme_point_hill_climbing,
    "extreme_point_simulated_annealing": solve_extreme_point_simulated_annealing,
    "maximal_space_best_fit": solve_maximal_space_best_fit,
    "milp_big_m": solve_milp_big_m,
}

_INVENTORY_SEARCH_ALGORITHMS = frozenset({
    "extreme_point_best_fit", "extreme_point_ffd", "maximal_space_best_fit",
})
_INVENTORY_ADAPTER = InventoryLevelAdapter(
    level_id="level_01",
    supported_algorithm_ids=_INVENTORY_SEARCH_ALGORITHMS,
    orientation_provider=fixed_orientation_provider(),
)


def execute_level_01(
    algorithm_id: str, items: list[Item], containers: list[Container], settings: dict[str, Any],
) -> AlgorithmOutcome:
    try:
        executor = LEVEL_01_EXECUTORS[algorithm_id]
    except KeyError as exc:
        available = ", ".join(sorted(LEVEL_01_EXECUTORS))
        raise ValueError(f"Level 1 algorithm {algorithm_id!r} is not implemented. Available: {available}") from exc
    validation = settings.get("validation", {})
    candidate_validator = lambda placements: validate_solution(
        items,
        containers,
        placements,
        coordinate_tolerance=float(
            validation.get("coordinate_tolerance_mm", 1e-4)
        ),
        weight_tolerance=float(validation.get("weight_tolerance_kg", 1e-6)),
    ).valid
    return _INVENTORY_ADAPTER.execute(
        algorithm_id=algorithm_id,
        items=items,
        containers=containers,
        settings=settings,
        executor=executor,
        candidate_validator=candidate_validator,
    )
