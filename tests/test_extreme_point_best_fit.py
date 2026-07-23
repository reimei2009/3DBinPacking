import pytest

from container_packing.algorithms.heuristics.extreme_point_best_fit import solve_level1
from container_packing.algorithms.heuristics.extreme_point_ffd import solve_level1 as solve_ffd
from container_packing.algorithms.feasibility import ExactSupportFeasibilityPolicy
from container_packing.algorithms.orientation import horizontal_orientation_provider
from container_packing.levels.level_01_validation import validate_solution
from container_packing.levels.level_03_validation import validate_solution as validate_level3
from container_packing.metrics import packing_tiebreak_metrics
from container_packing.schemas import Container, Item


def compactness_fixture():
    items = [Item("A", 4, 7, 2, 1), Item("B", 4, 3, 2, 1)]
    containers = [Container("C1", 10, 10, 2, 100, 10, volume_m3=2e-7)]
    return items, containers


def test_best_fit_evaluates_all_points_and_reduces_bounding_volume():
    items, containers = compactness_fixture()
    first_fit = solve_ffd(items, containers)
    best_fit = solve_level1(items, containers)
    assert best_fit.solve.status == "FEASIBLE"
    assert validate_solution(items, containers, best_fit.placements).valid
    assert packing_tiebreak_metrics(best_fit.placements)[0] < packing_tiebreak_metrics(first_fit.placements)[0]
    placement = next(value for value in best_fit.placements if value.item_id == "B")
    assert (placement.x_mm, placement.y_mm, placement.z_mm) == (0.0, 7.0, 0.0)
    assert best_fit.metadata["candidate_scoring"].startswith("open_container")
    assert best_fit.metadata["extreme_points_evaluated"] > first_fit.metadata["extreme_points_evaluated"]


def test_best_fit_is_deterministic_and_respects_payload():
    items = [Item("A", 5, 5, 5, 6), Item("B", 5, 5, 5, 6)]
    containers = [
        Container("C1", 10, 10, 10, 10, 10, volume_m3=1e-6),
        Container("C2", 10, 10, 10, 10, 20, volume_m3=1e-6),
    ]
    first = solve_level1(items, containers)
    second = solve_level1(items, containers)
    assert first.placements == second.placements
    assert {value.container_id for value in first.placements} == {"C1", "C2"}
    assert validate_solution(items, containers, first.placements).valid


def test_best_fit_failure_is_not_reported_as_proven_infeasible():
    item = Item("TOO_BIG", 11, 10, 10, 1)
    container = Container("C1", 10, 10, 10, 100, 10, volume_m3=1e-6)
    result = solve_level1([item], [container])
    assert result.solve.status == "INFEASIBLE_HEURISTIC"
    assert result.placements == []
    assert result.metadata["optimality_proven"] is False


def test_best_fit_rejects_invalid_subset_limit():
    items, containers = compactness_fixture()
    with pytest.raises(ValueError, match="subset_enumeration_limit"):
        solve_level1(items, containers, {"subset_enumeration_limit": 0})


def test_best_fit_uses_horizontal_orientation_when_fixed_orientation_cannot_fit():
    item = Item("A", 8, 12, 5, 1)
    containers = [Container("C", 12, 8, 5, 10, 1, volume_m3=0.00000048)]

    outcome = solve_level1([item], containers, orientation_provider=horizontal_orientation_provider())

    assert outcome.solve.status == "FEASIBLE"
    assert outcome.placements[0].orientation_code == "YXZ"
    assert validate_level3([item], containers, outcome.placements).result.valid
    assert outcome.metadata["orientation_candidates_evaluated"] >= 2


def test_best_fit_passes_rotated_candidates_through_exact_support_policy():
    items = [Item("BOTTOM", 10, 20, 5, 1), Item("TOP", 10, 20, 5, 1)]
    containers = [Container("C", 20, 10, 10, 10, 1, volume_m3=0.000002)]
    outcome = solve_level1(
        items, containers,
        policy=ExactSupportFeasibilityPolicy(0.8, 1e-4),
        orientation_provider=horizontal_orientation_provider(),
    )

    assert outcome.solve.status == "FEASIBLE"
    assert {placement.orientation_code for placement in outcome.placements} == {"YXZ"}
    assert validate_level3(items, containers, outcome.placements).result.valid
