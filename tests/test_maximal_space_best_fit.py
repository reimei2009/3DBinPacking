import pytest

from container_packing.algorithms.heuristics.extreme_point_best_fit import solve_level1 as solve_extreme_point
from container_packing.algorithms.heuristics.maximal_space_best_fit import solve_level1
from container_packing.algorithms.heuristics.maximal_space_core import (
    EmptySpace,
    contains_space,
    prune_maximal_spaces,
    spaces_intersect_box,
    subtract_placement,
    update_maximal_spaces,
)
from container_packing.levels.level_01_validation import validate_solution
from container_packing.schemas import Container, Item, Placement


def test_center_placement_splits_space_into_six_empty_slabs():
    space = EmptySpace(0, 0, 0, 10, 10, 10)
    placement = Placement("I1", "C1", 2, 3, 4, 4, 2, 3, 1)
    residual = subtract_placement(space, placement)
    assert len(residual) == 6
    assert all(not spaces_intersect_box(value, placement) for value in residual)
    assert {(value.x_mm, value.length_mm) for value in residual if value.width_mm == 10 and value.height_mm == 10} == {
        (0, 2), (6, 4),
    }
    assert {(value.y_mm, value.width_mm) for value in residual if value.length_mm == 10 and value.height_mm == 10} == {
        (0, 3), (5, 5),
    }
    assert {(value.z_mm, value.height_mm) for value in residual if value.length_mm == 10 and value.width_mm == 10} == {
        (0, 4), (7, 3),
    }


def test_pruning_removes_duplicates_and_contained_spaces():
    outer = EmptySpace(0, 0, 0, 10, 10, 10)
    inner = EmptySpace(1, 1, 1, 2, 2, 2)
    side = EmptySpace(10, 0, 0, 2, 2, 2)
    result = prune_maximal_spaces([outer, inner, outer, side])
    assert result == [outer, side]
    assert contains_space(outer, inner)


def test_update_keeps_only_spaces_not_occupied_by_new_placement():
    initial = [EmptySpace(0, 0, 0, 10, 10, 10)]
    placement = Placement("I1", "C1", 0, 0, 0, 4, 5, 6, 1)
    spaces, generated, pruned = update_maximal_spaces(initial, placement)
    assert generated == 3
    assert pruned == 0
    assert len(spaces) == 3
    assert all(not spaces_intersect_box(value, placement) for value in spaces)


def test_maximal_space_best_fit_is_deterministic_and_valid():
    items = [
        Item("A", 6, 4, 4, 2), Item("B", 4, 6, 4, 2), Item("C", 4, 4, 6, 2),
    ]
    containers = [Container("C1", 10, 10, 10, 100, 10, volume_m3=1e-6)]
    first = solve_level1(items, containers)
    second = solve_level1(items, containers)
    assert first.solve.status == "FEASIBLE"
    assert first.placements == second.placements
    assert first.metadata == second.metadata
    assert first.metadata["empty_spaces_evaluated"] > 0
    assert first.metadata["maximum_active_spaces"] > 0
    assert validate_solution(items, containers, first.placements).valid


def test_maximal_spaces_find_valid_geometry_missed_by_extreme_point_best_fit():
    items = [
        Item("I0", 4, 7, 6, 1), Item("I1", 6, 2, 7, 1),
        Item("I2", 7, 5, 3, 1), Item("I3", 7, 3, 6, 1),
        Item("I4", 5, 3, 3, 1),
    ]
    containers = [Container("C1", 10, 10, 10, 999, 10, volume_m3=1e-6)]
    extreme_point = solve_extreme_point(items, containers)
    maximal_space = solve_level1(items, containers)
    assert extreme_point.solve.status == "INFEASIBLE_HEURISTIC"
    assert maximal_space.solve.status == "FEASIBLE"
    assert validate_solution(items, containers, maximal_space.placements).valid


def test_payload_forces_two_containers():
    items = [Item("A", 5, 5, 5, 6), Item("B", 5, 5, 5, 6)]
    containers = [
        Container("C1", 10, 10, 10, 10, 10, volume_m3=1e-6),
        Container("C2", 10, 10, 10, 10, 20, volume_m3=1e-6),
    ]
    result = solve_level1(items, containers)
    assert {value.container_id for value in result.placements} == {"C1", "C2"}
    assert validate_solution(items, containers, result.placements).valid


def test_failure_does_not_claim_proven_infeasibility():
    item = Item("TOO_BIG", 11, 10, 10, 1)
    container = Container("C1", 10, 10, 10, 100, 10, volume_m3=1e-6)
    result = solve_level1([item], [container])
    assert result.solve.status == "INFEASIBLE_HEURISTIC"
    assert result.placements == []
    assert result.metadata["optimality_proven"] is False


def test_rejects_invalid_subset_limit():
    with pytest.raises(ValueError, match="subset_enumeration_limit"):
        solve_level1(
            [Item("A", 1, 1, 1, 1)],
            [Container("C1", 2, 2, 2, 10, 10, volume_m3=8e-9)],
            {"subset_enumeration_limit": 0},
        )
