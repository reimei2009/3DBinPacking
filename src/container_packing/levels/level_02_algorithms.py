"""Level 2 dispatch using shared engines with exact-support feasibility."""

from __future__ import annotations

from typing import Any, Callable

from ..algorithms.contracts import AlgorithmOutcome
from ..algorithms.exact.milp_big_m import solve_level2
from ..algorithms.feasibility import ExactSupportFeasibilityPolicy
from ..algorithms.heuristics.extreme_point_best_fit import solve as solve_extreme_point_best_fit
from ..algorithms.heuristics.extreme_point_ffd import solve as solve_extreme_point_ffd
from ..algorithms.heuristics.extreme_point_hill_climbing import solve as solve_extreme_point_hill_climbing
from ..algorithms.heuristics.maximal_space_best_fit import solve as solve_maximal_space_best_fit
from ..algorithms.metaheuristics.extreme_point_simulated_annealing import solve as solve_extreme_point_simulated_annealing
from ..algorithms.search import (
    ContainerSearchConfiguration,
    exact_support_closures,
    InventorySearchOrchestrator,
    InventorySearchRequest,
)
from ..schemas import Container, Item
from .level_02_validation import validate_solution

Level02Executor = Callable[[list[Item], list[Container], dict[str, Any]], AlgorithmOutcome]

_INVENTORY_SEARCH_ORCHESTRATOR = InventorySearchOrchestrator()
_INVENTORY_SEARCH_ALGORITHMS = frozenset({
    "extreme_point_best_fit", "extreme_point_ffd",
})


def execute_level_02(
    algorithm_id: str, items: list[Item], containers: list[Container], settings: dict[str, Any],
) -> AlgorithmOutcome:
    search = ContainerSearchConfiguration.from_mapping(settings.get("container_search"))
    if algorithm_id == "milp_big_m":
        if search.enabled:
            raise ValueError(
                "Inventory-aware container search currently supports only "
                "extreme_point_best_fit, extreme_point_ffd; disable "
                "container_search before selecting milp_big_m."
            )
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
    def execute_with_exact_support(
        selected_items: list[Item],
        selected_containers: list[Container],
        selected_settings: dict[str, Any],
        *,
        container_subset_policy: Any = None,
    ) -> AlgorithmOutcome:
        support = selected_settings.get("support", {})
        policy = ExactSupportFeasibilityPolicy(
            threshold=float(support.get("threshold", 0.8)),
            epsilon_mm=float(support.get("epsilon_mm", 1e-4)),
        )
        keyword_arguments: dict[str, Any] = {"policy": policy}
        if container_subset_policy is not None:
            keyword_arguments["container_subset_policy"] = container_subset_policy
        return executor(selected_items, selected_containers, selected_settings, **keyword_arguments)

    if not search.enabled:
        return execute_with_exact_support(items, containers, settings)
    support = settings.get("support", {})
    validation = settings.get("validation", {})
    support_epsilon = float(support.get("epsilon_mm", 1e-4))
    candidate_validator = lambda placements: validate_solution(
        items,
        containers,
        placements,
        support_threshold=float(support.get("threshold", 0.8)),
        support_epsilon_mm=support_epsilon,
        dense_grid_x=int(support.get("dense_grid_x", 20)),
        dense_grid_y=int(support.get("dense_grid_y", 20)),
        coordinate_tolerance=float(
            validation.get("coordinate_tolerance_mm", 1e-4)
        ),
        weight_tolerance=float(validation.get("weight_tolerance_kg", 1e-6)),
    ).result.valid
    return _INVENTORY_SEARCH_ORCHESTRATOR.execute(
        InventorySearchRequest(
            algorithm_id=algorithm_id,
            items=items,
            containers=containers,
            settings=settings,
            configuration=search,
            supported_algorithm_ids=_INVENTORY_SEARCH_ALGORITHMS,
            precheck_backend="inventory-aware-level-02-precheck",
            precheck_failure_context="Level 2 instance",
            support_closure_provider=lambda placements: exact_support_closures(
                placements, epsilon_mm=support_epsilon,
            ),
            candidate_validator=candidate_validator,
        ),
        execute_with_exact_support,
    )
