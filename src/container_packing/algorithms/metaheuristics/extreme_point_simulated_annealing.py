"""Seeded Simulated Annealing over fixed-orientation Extreme-Point packings."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import exp
from random import Random
from typing import Any

from scipy.optimize import OptimizeResult

from ..contracts import AlgorithmOutcome
from ..feasibility import FixedOrientationFeasibilityPolicy, PlacementFeasibilityPolicy
from ..orientation import OrientationProvider, fixed_orientation_provider
from ..heuristics.extreme_point_core import item_sort_key
from ..heuristics.extreme_point_ffd import solve as solve_extreme_point_ffd
from ..heuristics.extreme_point_neighborhood import (
    RepackingStats,
    generate_neighbor_orders,
    repack_neighbor,
    solution_score,
)
from ...schemas import Container, Item, Placement, SolveResult


@dataclass
class AnnealingStats(RepackingStats):
    iterations: int = 0
    neighbors_evaluated: int = 0
    accepted_moves: int = 0
    accepted_worse_moves: int = 0
    best_improvements: int = 0
    accepted_operator_counts: dict[str, int] = field(default_factory=dict)


def annealing_energy(score: tuple[float, ...], containers: list[Container]) -> float:
    """Map the lexicographic score to a temperature-scaled acceptance energy."""
    count, cost, bounding_volume, coordinate_score = score
    priority = 1.0 + sum(value.cost for value in containers)
    volume_scale = max(1.0, sum(value.volume_m3 for value in containers) * 1_000_000_000)
    max_span = max(1.0, max(value.length_mm + value.width_mm + value.height_mm for value in containers))
    return (
        count
        + cost / priority
        + 0.05 * bounding_volume / volume_scale
        + 0.0001 * coordinate_score / max_span
    )


def acceptance_probability(delta_energy: float, temperature: float) -> float:
    """Return the Metropolis acceptance probability for a non-improving move."""
    if temperature <= 0:
        raise ValueError("temperature must be positive")
    if delta_energy <= 0:
        return 1.0
    return exp(-delta_energy / temperature)


def _failure(baseline: AlgorithmOutcome) -> AlgorithmOutcome:
    return AlgorithmOutcome(
        solve=SolveResult(
            status="INFEASIBLE_HEURISTIC",
            message="Initial Extreme-Point FFD found no solution; Simulated Annealing was not started.",
            objective_value=None, vector=None, raw_result=OptimizeResult(),
        ),
        placements=[], backend="seeded/extreme-point-simulated-annealing",
        metadata={
            **baseline.metadata, "algorithm_kind": "metaheuristic",
            "optimality_proven": False, "annealing_iterations": 0,
            "neighbors_evaluated": 0, "repacking_attempts": 0,
            "accepted_moves": 0, "accepted_worse_moves": 0,
            "best_improvements": 0, "accepted_operator_counts": {},
        },
    )


def solve(
    items: list[Item], containers: list[Container], settings: dict[str, Any] | None = None,
    *, policy: PlacementFeasibilityPolicy | None = None,
    orientation_provider: OrientationProvider | None = None,
) -> AlgorithmOutcome:
    """Search item permutations while retaining the best valid packing found."""
    settings = settings or {}
    max_iterations = int(settings.get("max_iterations", 200))
    max_neighbors = int(settings.get("max_neighbors", 48))
    neighbors_per_iteration = int(settings.get("neighbors_per_iteration", 3))
    subset_candidate_limit = int(settings.get("subset_candidate_limit", 48))
    initial_temperature = float(settings.get("initial_temperature", 0.25))
    cooling_rate = float(settings.get("cooling_rate", 0.97))
    minimum_temperature = float(settings.get("minimum_temperature", 0.0001))
    random_seed = int(settings.get("random_seed", 42))
    if max_iterations < 0:
        raise ValueError("max_iterations must be non-negative")
    if max_neighbors <= 0 or neighbors_per_iteration <= 0 or subset_candidate_limit <= 0:
        raise ValueError("Simulated-Annealing neighborhood limits must be positive")
    if initial_temperature <= 0 or minimum_temperature <= 0 or minimum_temperature > initial_temperature:
        raise ValueError("Temperatures must be positive and minimum_temperature <= initial_temperature")
    if not 0 < cooling_rate < 1:
        raise ValueError("cooling_rate must be between 0 and 1")

    selected_policy = policy or FixedOrientationFeasibilityPolicy()
    selected_orientation_provider = orientation_provider or fixed_orientation_provider()
    baseline = solve_extreme_point_ffd(
        items, containers, settings,
        policy=selected_policy, orientation_provider=selected_orientation_provider,
    )
    if baseline.solve.status != "FEASIBLE":
        return _failure(baseline)

    rng = Random(random_seed)
    current = baseline.placements
    current_order = sorted(items, key=item_sort_key)
    current_score = solution_score(current, containers)
    current_energy = annealing_energy(current_score, containers)
    initial_score = current_score
    best = list(current)
    best_score = current_score
    stats = AnnealingStats()
    final_temperature = initial_temperature
    annealing_settings = {**settings, "allow_worse_subsets": True}

    for iteration in range(max_iterations):
        temperature = max(minimum_temperature, initial_temperature * (cooling_rate ** iteration))
        final_temperature = temperature
        neighbors = generate_neighbor_orders(current_order, current, max_neighbors)
        if not neighbors:
            break
        indices = list(range(len(neighbors)))
        rng.shuffle(indices)
        candidate_data: tuple[str, list[Item], list[Placement]] | None = None
        for index in indices[:neighbors_per_iteration]:
            operator, neighbor_order = neighbors[index]
            stats.neighbors_evaluated += 1
            candidate = repack_neighbor(
                neighbor_order, containers, current, annealing_settings, stats, selected_policy,
                orientation_provider=selected_orientation_provider,
            )
            if candidate is not None:
                candidate_data = operator, neighbor_order, candidate
                break
        stats.iterations += 1
        if candidate_data is None:
            continue

        operator, neighbor_order, candidate = candidate_data
        candidate_score = solution_score(candidate, containers)
        candidate_energy = annealing_energy(candidate_score, containers)
        delta = candidate_energy - current_energy
        if delta <= 0 or rng.random() < acceptance_probability(delta, temperature):
            if delta > 0:
                stats.accepted_worse_moves += 1
            stats.accepted_moves += 1
            stats.accepted_operator_counts[operator] = stats.accepted_operator_counts.get(operator, 0) + 1
            current_order, current = neighbor_order, candidate
            current_score, current_energy = candidate_score, candidate_energy
            if candidate_score < best_score:
                best, best_score = list(candidate), candidate_score
                stats.best_improvements += 1

    used_ids = {value.container_id for value in best}
    priority = 1.0 + sum(value.cost for value in containers)
    total_cost = sum(value.cost for value in containers if value.container_id in used_ids)
    objective = len(used_ids) * priority + total_cost
    solve = SolveResult(
        status="FEASIBLE",
        message="Seeded Extreme-Point Simulated Annealing found a complete packing.",
        objective_value=float(objective), vector=None, raw_result=OptimizeResult(),
    )
    return AlgorithmOutcome(
        solve=solve, placements=best, backend="seeded/extreme-point-simulated-annealing",
        metadata={
            "algorithm_kind": "metaheuristic",
            "optimality_proven": False,
            "initial_algorithm": "extreme_point_ffd",
            "neighborhoods": ["relocate", "swap", "reinsert", "container_elimination"],
            "acceptance": "metropolis_with_lexicographic_best_retention",
            "allow_worse_subsets": True,
            "random_seed": random_seed,
            "max_iterations": max_iterations,
            "max_neighbors": max_neighbors,
            "neighbors_per_iteration": neighbors_per_iteration,
            "subset_candidate_limit": subset_candidate_limit,
            "initial_temperature": initial_temperature,
            "cooling_rate": cooling_rate,
            "minimum_temperature": minimum_temperature,
            "final_temperature": final_temperature,
            "annealing_iterations": stats.iterations,
            "neighbors_evaluated": stats.neighbors_evaluated,
            "repacking_attempts": stats.repacking_attempts,
            "accepted_moves": stats.accepted_moves,
            "accepted_worse_moves": stats.accepted_worse_moves,
            "best_improvements": stats.best_improvements,
            "accepted_operator_counts": stats.accepted_operator_counts,
            "initial_score": list(initial_score),
            "final_current_score": list(current_score),
            "best_score": list(best_score),
            "improved": best_score < initial_score,
            "n_items": len(items),
            "n_containers": len(containers),
            **selected_orientation_provider.metadata(),
            **selected_policy.metadata(),
        },
    )


solve_level1 = solve
