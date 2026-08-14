"""Level 3 dispatch: horizontal orientation with exact geometric support."""

from __future__ import annotations

from typing import Any, Callable

from ..algorithms.contracts import AlgorithmOutcome
from ..algorithms.feasibility import ExactSupportFeasibilityPolicy
from ..algorithms.exact.milp_big_m import solve_level3
from ..algorithms.heuristics.extreme_point_best_fit import solve as solve_extreme_point_best_fit
from ..algorithms.heuristics.extreme_point_ffd import solve as solve_extreme_point_ffd
from ..algorithms.heuristics.extreme_point_hill_climbing import solve as solve_extreme_point_hill_climbing
from ..algorithms.heuristics.maximal_space_best_fit import solve as solve_maximal_space_best_fit
from ..algorithms.metaheuristics.extreme_point_simulated_annealing import solve as solve_extreme_point_simulated_annealing
from ..algorithms.orientation import horizontal_orientation_provider
from ..algorithms.search import (
    ContainerSearchConfiguration,
    exact_support_closures,
    InventoryLevelAdapter,
)
from ..schemas import Container, Item
from .level_03_validation import validate_solution

Level03Executor = Callable[[list[Item], list[Container], dict[str, Any]], AlgorithmOutcome]

_INVENTORY_SEARCH_ALGORITHMS = frozenset({
    "extreme_point_best_fit", "extreme_point_ffd", "maximal_space_best_fit",
})
_HORIZONTAL_ORIENTATION_PROVIDER = horizontal_orientation_provider()
_INVENTORY_ADAPTER = InventoryLevelAdapter(
    level_id="level_03",
    supported_algorithm_ids=_INVENTORY_SEARCH_ALGORITHMS,
    orientation_provider=_HORIZONTAL_ORIENTATION_PROVIDER,
)


def execute_level_03(
    algorithm_id: str, items: list[Item], containers: list[Container], settings: dict[str, Any]
):
    search = ContainerSearchConfiguration.from_mapping(settings.get("container_search"))
    if algorithm_id == "milp_big_m":
        if search.enabled:
            raise ValueError(
                "Level 3 inventory-aware search supports only extreme_point_best_fit, "
                "extreme_point_ffd and maximal_space_best_fit; disable container_search "
                "before selecting milp_big_m."
            )
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
    def execute_with_horizontal_support(
        selected_items: list[Item],
        selected_containers: list[Container],
        selected_settings: dict[str, Any],
        *,
        container_subset_policy: Any = None,
    ) -> AlgorithmOutcome:
        selected_support = selected_settings.get("support", {})
        policy = ExactSupportFeasibilityPolicy(
            threshold=float(selected_support.get("threshold", 0.8)),
            epsilon_mm=float(selected_support.get("epsilon_mm", 1e-4)),
            policy_id="horizontal_orientation_geometry_payload_exact_support",
        )
        keyword_arguments: dict[str, Any] = {
            "policy": policy,
            "orientation_provider": _HORIZONTAL_ORIENTATION_PROVIDER,
        }
        if container_subset_policy is not None:
            keyword_arguments["container_subset_policy"] = container_subset_policy
        return executor(
            selected_items,
            selected_containers,
            selected_settings,
            **keyword_arguments,
        )

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
    return _INVENTORY_ADAPTER.execute(
        algorithm_id=algorithm_id,
        items=items,
        containers=containers,
        settings=settings,
        executor=execute_with_horizontal_support,
        support_closure_provider=lambda placements: exact_support_closures(
            placements, epsilon_mm=support_epsilon,
        ),
        candidate_validator=candidate_validator,
        secondary_support_threshold=float(support.get("threshold", 0.8)),
        secondary_support_epsilon_mm=support_epsilon,
    )
