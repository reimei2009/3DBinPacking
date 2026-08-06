"""Single dispatch table for Level 1 algorithm implementations."""

from __future__ import annotations

from typing import Any, Callable

from ..algorithms.contracts import AlgorithmOutcome
from ..algorithms.search import (
    ContainerSearchConfiguration,
    InventorySearchOrchestrator,
    InventorySearchRequest,
)
from ..algorithms.exact.milp_big_m import solve_level1 as solve_milp_big_m
from ..algorithms.heuristics.extreme_point_best_fit import solve as solve_extreme_point_best_fit
from ..algorithms.heuristics.extreme_point_ffd import solve as solve_extreme_point_ffd
from ..algorithms.heuristics.extreme_point_ffd_gap_fill import solve as solve_extreme_point_ffd_gap_fill
from ..algorithms.heuristics.extreme_point_hill_climbing import solve as solve_extreme_point_hill_climbing
from ..algorithms.heuristics.maximal_space_best_fit import solve as solve_maximal_space_best_fit
from ..algorithms.metaheuristics.extreme_point_simulated_annealing import solve as solve_extreme_point_simulated_annealing
from ..schemas import Container, Item

Level01Executor = Callable[[list[Item], list[Container], dict[str, Any] | None], AlgorithmOutcome]

LEVEL_01_EXECUTORS: dict[str, Level01Executor] = {
    "extreme_point_best_fit": solve_extreme_point_best_fit,
    "extreme_point_ffd": solve_extreme_point_ffd,
    "extreme_point_ffd_gap_fill": solve_extreme_point_ffd_gap_fill,
    "extreme_point_hill_climbing": solve_extreme_point_hill_climbing,
    "extreme_point_simulated_annealing": solve_extreme_point_simulated_annealing,
    "maximal_space_best_fit": solve_maximal_space_best_fit,
    "milp_big_m": solve_milp_big_m,
}

_INVENTORY_SEARCH_ORCHESTRATOR = InventorySearchOrchestrator()
_INVENTORY_SEARCH_ALGORITHMS = frozenset({
    "extreme_point_best_fit", "extreme_point_ffd",
})


def execute_level_01(
    algorithm_id: str, items: list[Item], containers: list[Container], settings: dict[str, Any],
) -> AlgorithmOutcome:
    try:
        executor = LEVEL_01_EXECUTORS[algorithm_id]
    except KeyError as exc:
        available = ", ".join(sorted(LEVEL_01_EXECUTORS))
        raise ValueError(f"Level 1 algorithm {algorithm_id!r} is not implemented. Available: {available}") from exc
    search = ContainerSearchConfiguration.from_mapping(
        settings.get("container_search")
    )
    if not search.enabled:
        return executor(items, containers, settings)
    return _INVENTORY_SEARCH_ORCHESTRATOR.execute(
        InventorySearchRequest(
            algorithm_id=algorithm_id,
            items=items,
            containers=containers,
            settings=settings,
            configuration=search,
            supported_algorithm_ids=_INVENTORY_SEARCH_ALGORITHMS,
            precheck_backend="inventory-aware-level-01-precheck",
            precheck_failure_context="Level 1 instance",
        ),
        executor,
    )
