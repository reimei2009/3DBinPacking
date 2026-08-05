"""Single dispatch table for Level 1 algorithm implementations."""

from __future__ import annotations

from dataclasses import asdict
from time import perf_counter
from typing import Any, Callable

from scipy.optimize import OptimizeResult

from ..algorithms.contracts import AlgorithmOutcome
from ..algorithms.search import (
    ContainerSearchConfiguration,
    LazyRankedContainerSubsetPolicy,
    estimate_container_lower_bound,
    normalize_container_inventory,
    run_hard_precheck,
)
from ..algorithms.exact.milp_big_m import solve_level1 as solve_milp_big_m
from ..algorithms.heuristics.extreme_point_best_fit import solve as solve_extreme_point_best_fit
from ..algorithms.heuristics.extreme_point_ffd import solve as solve_extreme_point_ffd
from ..algorithms.heuristics.extreme_point_hill_climbing import solve as solve_extreme_point_hill_climbing
from ..algorithms.heuristics.maximal_space_best_fit import solve as solve_maximal_space_best_fit
from ..algorithms.metaheuristics.extreme_point_simulated_annealing import solve as solve_extreme_point_simulated_annealing
from ..schemas import Container, Item, SolveResult

Level01Executor = Callable[[list[Item], list[Container], dict[str, Any] | None], AlgorithmOutcome]

LEVEL_01_EXECUTORS: dict[str, Level01Executor] = {
    "extreme_point_best_fit": solve_extreme_point_best_fit,
    "extreme_point_ffd": solve_extreme_point_ffd,
    "extreme_point_hill_climbing": solve_extreme_point_hill_climbing,
    "extreme_point_simulated_annealing": solve_extreme_point_simulated_annealing,
    "maximal_space_best_fit": solve_maximal_space_best_fit,
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
    search = ContainerSearchConfiguration.from_mapping(
        settings.get("container_search")
    )
    if not search.enabled:
        return executor(items, containers, settings)
    if algorithm_id not in {"extreme_point_best_fit", "extreme_point_ffd"}:
        raise ValueError(
            "Level 1 inventory-aware container search currently supports only "
            "extreme_point_best_fit and extreme_point_ffd; disable container_search "
            f"or select a supported algorithm instead of {algorithm_id!r}."
        )

    inventory = normalize_container_inventory(containers)
    if search.limits.max_used_container_count > inventory.physical_container_count:
        raise ValueError(
            "container_search.max_used_container_count="
            f"{search.limits.max_used_container_count} exceeds the available physical "
            f"inventory ({inventory.physical_container_count})."
        )
    precheck = run_hard_precheck(items, inventory)
    lower_bound = estimate_container_lower_bound(items, inventory)
    shared_metadata = {
        **search.metadata(),
        **inventory.metadata(),
        **lower_bound.metadata(),
        "hard_precheck_valid": precheck.valid,
        "hard_precheck_issue_count": len(precheck.issues),
        "hard_precheck_issues": [asdict(value) for value in precheck.issues],
        "hide_objective_when_invalid": True,
    }
    if not precheck.valid:
        return AlgorithmOutcome(
            solve=SolveResult(
                status="PRECHECK_FAILED",
                message=(
                    "Hard input/capacity precheck rejected the Level 1 instance: "
                    + "; ".join(value.message for value in precheck.issues)
                ),
                objective_value=None,
                vector=None,
                raw_result=OptimizeResult(),
            ),
            placements=[],
            backend="inventory-aware-level-01-precheck",
            metadata={
                **shared_metadata,
                "failure_interpretation": "proven_input_or_aggregate_capacity_failure",
                "construction_complete": False,
                "construction_termination_reason": "hard_precheck_failed",
                "unpacked_item_count": len(items),
                "unpacked_items": [
                    {
                        "item_id": value.item_id,
                        "reason_code": "HARD_PRECHECK_FAILED",
                    }
                    for value in items
                ],
            },
        )

    deadline = (
        None
        if search.time_limit_seconds is None
        else perf_counter() + search.time_limit_seconds
    )
    policy = LazyRankedContainerSubsetPolicy(
        search.limits,
        exhaustive_max_containers=search.exhaustive_max_containers,
        max_candidates_per_count=search.max_candidates_per_count,
        neighborhood_width=search.neighborhood_width,
        soft_volume_buffer_ratio=search.soft_volume_buffer_ratio,
        deadline_monotonic=deadline,
    )
    selected_settings = dict(settings)
    if deadline is not None:
        selected_settings["constructive_deadline_monotonic"] = deadline
    outcome = executor(
        items,
        containers,
        selected_settings,
        container_subset_policy=policy,
    )
    final_metadata = {**outcome.metadata, **shared_metadata, **policy.metadata()}
    if outcome.solve.status in {"INFEASIBLE_HEURISTIC", "TIME_LIMIT"}:
        if lower_bound.aggregate_lower_bound > max(search.limits.cardinalities):
            reason = "container_count_limit_below_aggregate_lower_bound"
            item_reason = "CONTAINER_COUNT_LIMIT_BELOW_LOWER_BOUND"
        elif outcome.solve.status == "TIME_LIMIT":
            reason = "time_limit_reached"
            item_reason = "TIME_LIMIT_REACHED"
        else:
            reason = "heuristic_search_exhausted"
            item_reason = "NO_COMPLETE_PACKING_FOUND"
        final_metadata.setdefault("construction_complete", False)
        final_metadata.setdefault("construction_termination_reason", reason)
        final_metadata.setdefault("unpacked_item_count", len(items))
        final_metadata.setdefault("unpacked_items", [
            {"item_id": value.item_id, "reason_code": item_reason}
            for value in items
        ])
    return AlgorithmOutcome(
        solve=outcome.solve,
        placements=outcome.placements,
        backend=outcome.backend,
        metadata=final_metadata,
    )
