"""Deterministic destroy-and-repair hill climbing over Extreme-Point packings."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from scipy.optimize import OptimizeResult

from ..contracts import AlgorithmOutcome
from ..feasibility import FixedOrientationFeasibilityPolicy, PlacementFeasibilityPolicy
from ..orientation import OrientationProvider, fixed_orientation_provider
from ...schemas import Container, Item, SolveResult
from .construction_strategies import get_construction_strategy
from .extreme_point_core import item_sort_key
from .extreme_point_neighborhood import (
    RepackingStats,
    generate_neighbor_orders,
    repack_neighbor,
    solution_score,
)


@dataclass
class HillClimbingStats(RepackingStats):
    iterations: int = 0
    neighbors_evaluated: int = 0
    feasible_neighbors: int = 0
    rejected_neighbors: int = 0
    accepted_operators: list[str] = field(default_factory=list)


def solve(
    items: list[Item], containers: list[Container], settings: dict[str, Any] | None = None,
    *, policy: PlacementFeasibilityPolicy | None = None,
    orientation_provider: OrientationProvider | None = None,
) -> AlgorithmOutcome:
    settings = settings or {}
    max_iterations = int(settings.get("max_iterations", 10))
    max_neighbors = int(settings.get("max_neighbors", 24))
    subset_candidate_limit = int(settings.get("subset_candidate_limit", 48))
    if max_iterations < 0 or max_neighbors <= 0 or subset_candidate_limit <= 0:
        raise ValueError("Hill-climbing limits must be non-negative/positive")

    selected_policy = policy or FixedOrientationFeasibilityPolicy()
    selected_orientation_provider = orientation_provider or fixed_orientation_provider()
    initial_constructor = str(settings.get("initial_constructor", "extreme_point_ffd"))
    repair_constructor = str(settings.get("repair_constructor", initial_constructor))
    initial_strategy = get_construction_strategy(initial_constructor)
    repair_strategy = get_construction_strategy(repair_constructor)
    baseline = initial_strategy.initial(
        items, containers, settings,
        policy=selected_policy, orientation_provider=selected_orientation_provider,
    )
    if baseline.solve.status != "FEASIBLE":
        return AlgorithmOutcome(
            solve=SolveResult(
                status="INFEASIBLE_HEURISTIC",
                message=f"Initial constructor {initial_constructor} found no solution; hill climbing was not started.",
                objective_value=None, vector=None, raw_result=OptimizeResult(),
            ),
            placements=[], backend="deterministic/extreme-point-hill-climbing",
            metadata={
                **baseline.metadata, "algorithm_kind": "local_search",
                "optimality_proven": False, "hill_climbing_iterations": 0,
                "neighbors_evaluated": 0, "feasible_neighbors": 0,
                "rejected_neighbors": 0, "repacking_attempts": 0,
                "initial_algorithm": initial_constructor,
                "initial_constructor": initial_constructor, "repair_constructor": repair_constructor,
                "accepted_operators": [],
            },
        )

    current = baseline.placements
    current_order = sorted(items, key=item_sort_key)
    initial_score = solution_score(current, containers)
    current_score = initial_score
    stats = HillClimbingStats()
    for _ in range(max_iterations):
        best: tuple[tuple[float, ...], str, list[Item], list[Placement]] | None = None
        for operator, neighbor_order in generate_neighbor_orders(current_order, current, max_neighbors):
            stats.neighbors_evaluated += 1
            candidate = repack_neighbor(
                neighbor_order, containers, current, settings, stats, selected_policy,
                orientation_provider=selected_orientation_provider,
                construction_strategy=repair_strategy,
            )
            if candidate is None:
                stats.rejected_neighbors += 1
                continue
            stats.feasible_neighbors += 1
            score = solution_score(candidate, containers)
            if score < current_score and (best is None or score < best[0]):
                best = score, operator, neighbor_order, candidate
        if best is None:
            break
        current_score, operator, current_order, current = best
        stats.iterations += 1
        stats.accepted_operators.append(operator)

    used_ids = {value.container_id for value in current}
    priority = 1.0 + sum(value.cost for value in containers)
    total_cost = sum(value.cost for value in containers if value.container_id in used_ids)
    objective = len(used_ids) * priority + total_cost
    solve = SolveResult(
        status="FEASIBLE",
        message="Deterministic Extreme-Point hill climbing found a complete packing.",
        objective_value=float(objective), vector=None, raw_result=OptimizeResult(),
    )
    return AlgorithmOutcome(
        solve=solve, placements=current, backend="deterministic/extreme-point-hill-climbing",
        metadata={
            "algorithm_kind": "local_search",
            "optimality_proven": False,
            "initial_algorithm": initial_constructor,
            "initial_constructor": initial_constructor,
            "repair_constructor": repair_constructor,
            "neighborhoods": ["relocate", "swap", "reinsert", "container_elimination"],
            "acceptance": "steepest_lexicographic_improvement",
            "max_iterations": max_iterations,
            "max_neighbors": max_neighbors,
            "subset_candidate_limit": subset_candidate_limit,
            "hill_climbing_iterations": stats.iterations,
            "neighbors_evaluated": stats.neighbors_evaluated,
            "feasible_neighbors": stats.feasible_neighbors,
            "rejected_neighbors": stats.rejected_neighbors,
            "repacking_attempts": stats.repacking_attempts,
            "accepted_operators": stats.accepted_operators,
            "initial_score": list(initial_score),
            "final_score": list(current_score),
            "improved": current_score < initial_score,
            "n_items": len(items),
            "n_containers": len(containers),
            **selected_orientation_provider.metadata(),
            **selected_policy.metadata(),
        },
    )


solve_level1 = solve
