from math import isclose

import pytest

from container_packing.algorithms.heuristics.extreme_point_ffd import solve_level1 as solve_ffd
from container_packing.algorithms.heuristics.extreme_point_neighborhood import solution_score
from container_packing.algorithms.metaheuristics.extreme_point_simulated_annealing import (
    acceptance_probability,
    solve_level1 as solve_simulated_annealing,
)
from container_packing.levels.level_01_validation import validate_solution
from container_packing.schemas import Container, Item


def fixture():
    sizes = [(4, 6), (2, 7), (3, 8), (6, 5), (5, 2), (7, 3)]
    items = [Item(f"I{i}", length, width, 1, 1) for i, (length, width) in enumerate(sizes)]
    containers = [Container(f"C{i}", 10, 10, 1, 999, 10, volume_m3=1e-7) for i in range(1, 5)]
    return items, containers


def test_metropolis_probability_accepts_improvement_and_decays():
    assert acceptance_probability(-1.0, 1.0) == 1.0
    assert isclose(acceptance_probability(1.0, 1.0), 0.36787944117144233)
    assert acceptance_probability(1.0, 0.5) < acceptance_probability(1.0, 1.0)


def test_simulated_annealing_is_seeded_valid_and_retains_best():
    items, containers = fixture()
    settings = {
        "random_seed": 7, "max_iterations": 50, "max_neighbors": 32,
        "neighbors_per_iteration": 3,
    }
    baseline = solve_ffd(items, containers)
    first = solve_simulated_annealing(items, containers, settings)
    second = solve_simulated_annealing(items, containers, settings)
    assert first.solve.status == "FEASIBLE"
    assert first.placements == second.placements
    assert first.metadata == second.metadata
    assert first.metadata["random_seed"] == 7
    assert first.metadata["allow_worse_subsets"] is True
    assert sum(first.metadata["accepted_operator_counts"].values()) == first.metadata["accepted_moves"]
    assert solution_score(first.placements, containers) <= solution_score(baseline.placements, containers)
    assert validate_solution(items, containers, first.placements).valid


def test_zero_iterations_returns_valid_ffd_baseline():
    items, containers = fixture()
    outcome = solve_simulated_annealing(items, containers, {"max_iterations": 0})
    assert outcome.metadata["annealing_iterations"] == 0
    assert validate_solution(items, containers, outcome.placements).valid


@pytest.mark.parametrize("settings", [
    {"initial_temperature": 0}, {"cooling_rate": 1},
    {"minimum_temperature": 2, "initial_temperature": 1},
    {"neighbors_per_iteration": 0},
])
def test_rejects_invalid_settings(settings):
    items, containers = fixture()
    with pytest.raises(ValueError):
        solve_simulated_annealing(items, containers, settings)


def test_failed_initial_construction_is_not_claimed_infeasible_proof():
    item = Item("TOO_BIG", 21, 10, 10, 1)
    container = Container("C", 20, 10, 10, 100, 10, volume_m3=2e-6)
    outcome = solve_simulated_annealing([item], [container])
    assert outcome.solve.status == "INFEASIBLE_HEURISTIC"
    assert outcome.metadata["optimality_proven"] is False
