from container_packing.algorithms.heuristics.extreme_point_ffd import solve_level1
from container_packing.levels.level_01_validation import validate_solution
from container_packing.schemas import Container, Item


def container(container_id: str, *, payload: float = 100, cost: float = 10) -> Container:
    return Container(container_id, 20, 10, 10, payload, cost, volume_m3=0.000002)


def test_packs_touching_items_deterministically_without_rotation():
    items = [Item("A", 10, 10, 10, 2), Item("B", 10, 10, 10, 2)]
    first = solve_level1(items, [container("C")])
    second = solve_level1(items, [container("C")])
    assert first.solve.status == "FEASIBLE"
    assert first.placements == second.placements
    assert validate_solution(items, [container("C")], first.placements).valid
    assert {(value.length_mm, value.width_mm, value.height_mm) for value in first.placements} == {(10, 10, 10)}


def test_payload_forces_two_containers():
    items = [Item("A", 10, 10, 10, 6), Item("B", 10, 10, 10, 6)]
    containers = [container("C1", payload=10, cost=10), container("C2", payload=10, cost=20)]
    outcome = solve_level1(items, containers)
    assert outcome.solve.status == "FEASIBLE"
    assert {value.container_id for value in outcome.placements} == {"C1", "C2"}
    assert validate_solution(items, containers, outcome.placements).valid


def test_no_packing_is_not_reported_as_proven_infeasible():
    items = [Item("TOO_BIG", 21, 10, 10, 1)]
    outcome = solve_level1(items, [container("C")])
    assert outcome.solve.status == "INFEASIBLE_HEURISTIC"
    assert outcome.placements == []
    assert outcome.metadata["optimality_proven"] is False
