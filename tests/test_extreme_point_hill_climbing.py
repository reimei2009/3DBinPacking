from container_packing.algorithms.heuristics.extreme_point_ffd import solve_level1 as solve_ffd
from container_packing.algorithms.heuristics.extreme_point_hill_climbing import (
    solve_level1 as solve_hill_climbing,
)
from container_packing.algorithms.feasibility import ExactSupportFeasibilityPolicy
from container_packing.algorithms.orientation import horizontal_orientation_provider
from container_packing.algorithms.heuristics.extreme_point_neighborhood import (
    generate_neighbor_orders,
    solution_score,
)
from container_packing.levels.level_01_validation import validate_solution
from container_packing.levels.level_03_validation import validate_solution as validate_level3
from container_packing.schemas import Container, Item


def improvement_fixture():
    sizes = [(4, 6), (2, 7), (3, 8), (6, 5), (5, 2), (7, 3)]
    items = [Item(f"I{i}", length, width, 1, 1) for i, (length, width) in enumerate(sizes)]
    containers = [
        Container(f"C{i}", 10, 10, 1, 999, 10, volume_m3=1e-7)
        for i in range(1, 5)
    ]
    return items, containers


def test_neighbor_generation_exposes_relocate_swap_and_reinsert():
    items, containers = improvement_fixture()
    baseline = solve_ffd(items, containers)
    labels = {label.split("_from_")[0] for label, _ in generate_neighbor_orders(items, baseline.placements, 50)}
    assert "relocate" in labels
    assert "swap_adjacent" in labels
    assert "reinsert_front" in labels
    assert "reinsert_back" in labels


def test_hill_climbing_eliminates_a_container_and_is_deterministic():
    items, containers = improvement_fixture()
    baseline = solve_ffd(items, containers)
    first = solve_hill_climbing(items, containers)
    second = solve_hill_climbing(items, containers)
    assert solution_score(baseline.placements, containers)[:2] == (3.0, 30.0)
    assert solution_score(first.placements, containers)[:2] == (2.0, 20.0)
    assert first.placements == second.placements
    assert first.metadata["improved"] is True
    assert first.metadata["accepted_operators"]
    assert validate_solution(items, containers, first.placements).valid


def test_zero_iterations_preserves_valid_baseline():
    items, containers = improvement_fixture()
    outcome = solve_hill_climbing(items, containers, {"max_iterations": 0})
    assert outcome.solve.status == "FEASIBLE"
    assert outcome.metadata["hill_climbing_iterations"] == 0
    assert validate_solution(items, containers, outcome.placements).valid


def test_hill_climbing_repack_neighborhoods_preserve_horizontal_orientation_and_support():
    items = [Item("BOTTOM", 10, 20, 5, 1), Item("TOP", 10, 20, 5, 1)]
    containers = [Container("C", 20, 10, 10, 10, 1, volume_m3=0.000002)]
    outcome = solve_hill_climbing(
        items, containers,
        {"max_iterations": 1, "max_neighbors": 4, "subset_candidate_limit": 4},
        policy=ExactSupportFeasibilityPolicy(0.8, 1e-4),
        orientation_provider=horizontal_orientation_provider(),
    )

    assert outcome.solve.status == "FEASIBLE"
    assert outcome.metadata["repacking_attempts"] > 0
    assert outcome.metadata["orientation_profile"] == "horizontal_rotatable"
    assert {placement.orientation_code for placement in outcome.placements} == {"YXZ"}
    assert validate_level3(items, containers, outcome.placements).result.valid
