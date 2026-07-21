"""Deterministic destroy-and-repair hill climbing over Extreme-Point packings."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from scipy.optimize import OptimizeResult

from ..contracts import AlgorithmOutcome
from ...schemas import Container, Item, SolveResult
from .extreme_point_core import item_sort_key
from .extreme_point_ffd import solve_level1 as solve_extreme_point_ffd
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
    accepted_operators: list[str] = field(default_factory=list)


def solve_level1(
    items: list[Item], containers: list[Container], settings: dict[str, Any] | None = None,
) -> AlgorithmOutcome:
    settings = settings or {}
    max_iterations = int(settings.get("max_iterations", 10))
    max_neighbors = int(settings.get("max_neighbors", 24))
    subset_candidate_limit = int(settings.get("subset_candidate_limit", 48))
    if max_iterations < 0 or max_neighbors <= 0 or subset_candidate_limit <= 0:
        raise ValueError("Hill-climbing limits must be non-negative/positive")

    baseline = solve_extreme_point_ffd(items, containers, settings)
    if baseline.solve.status != "FEASIBLE":
        return AlgorithmOutcome(
            solve=SolveResult(
                status="INFEASIBLE_HEURISTIC",
                message="Initial Extreme-Point FFD found no solution; hill climbing was not started.",
                objective_value=None, vector=None, raw_result=OptimizeResult(),
            ),
            placements=[], backend="deterministic/extreme-point-hill-climbing",
            metadata={
                **baseline.metadata, "algorithm_kind": "local_search",
                "optimality_proven": False, "hill_climbing_iterations": 0,
                "neighbors_evaluated": 0, "repacking_attempts": 0,
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
            candidate = repack_neighbor(neighbor_order, containers, current, settings, stats)
            if candidate is None:
                continue
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
            "initial_algorithm": "extreme_point_ffd",
            "neighborhoods": ["relocate", "swap", "reinsert", "container_elimination"],
            "acceptance": "steepest_lexicographic_improvement",
            "max_iterations": max_iterations,
            "max_neighbors": max_neighbors,
            "subset_candidate_limit": subset_candidate_limit,
            "hill_climbing_iterations": stats.iterations,
            "neighbors_evaluated": stats.neighbors_evaluated,
            "repacking_attempts": stats.repacking_attempts,
            "accepted_operators": stats.accepted_operators,
            "initial_score": list(initial_score),
            "final_score": list(current_score),
            "improved": current_score < initial_score,
            "n_items": len(items),
            "n_containers": len(containers),
        },
    )
