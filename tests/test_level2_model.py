import pytest

from container_packing.algorithms.exact.milp_big_m import extract_placements, solve_level2, solve_milp
from container_packing.levels.level_02_validation import validate_solution
from container_packing.models.level_02.milp_model import build_level2_model
from container_packing.models.level_02.model_indices import Level02ModelIndices
from container_packing.schemas import Container, Item


def test_level2_indices_are_contiguous():
    indices = Level02ModelIndices(3, 2, 2, 2)
    values = set(range(indices.base.n_variables))
    values |= {indices.floor(i, k) for i in range(3) for k in range(2)}
    values |= {
        indices.support_point(i, j, k, p, q)
        for i in range(3) for j in range(3) if i != j
        for k in range(2) for p in range(2) for q in range(2)
    }
    values |= {indices.center_support(i, j, k) for i in range(3) for j in range(3) if i != j for k in range(2)}
    assert values == set(range(indices.n_variables))


def test_level2_milp_forces_full_footprint_stack_and_validates():
    items = [Item("A", 10, 10, 5, 1), Item("B", 10, 10, 5, 1)]
    containers = [Container("C", 10, 10, 10, 10, 1, volume_m3=1e-6)]
    problem = build_level2_model(items, containers, {"grid_x": 4, "grid_y": 4, "threshold": 0.8})
    solved = solve_milp(problem, {"time_limit_seconds": 10, "display": False})
    placements = extract_placements(solved, problem, items, containers, tolerance=1e-4)
    checked = validate_solution(items, containers, placements)
    assert solved.status == "OPTIMAL"
    assert checked.result.valid
    assert sorted(value.z_mm for value in placements) == pytest.approx([0, 5])
    assert sorted(record.exact_support_ratio for record in checked.support_records) == [1, 1]
    assert problem.metadata["support_point_variable_count"] == 32


def test_level2_one_item_uses_floor_without_support_pair_variables():
    items = [Item("A", 5, 5, 5, 1)]
    containers = [Container("C", 10, 10, 10, 10, 1, volume_m3=1e-6)]
    problem = build_level2_model(items, containers, {"grid_x": 4, "grid_y": 4, "threshold": 0.8})
    solved = solve_milp(problem, {"time_limit_seconds": 10})
    placements = extract_placements(solved, problem, items, containers, tolerance=1e-4)
    assert solved.status == "OPTIMAL"
    assert placements[0].z_mm == 0
    assert problem.metadata["support_point_variable_count"] == 0
    assert problem.metadata["capacity_strengthening_enabled"] is True
    assert problem.metadata["capacity_strengthening_cut_count"] == 4
    assert problem.metadata["container_count_lower_bound"] == 1


def test_level2_capacity_cuts_detect_payload_container_lower_bound():
    items = [Item("A", 1, 1, 1, 6), Item("B", 1, 1, 1, 6)]
    containers = [
        Container("C1", 10, 10, 10, 10, 1),
        Container("C2", 10, 10, 10, 10, 1),
    ]
    problem = build_level2_model(items, containers, {"grid_x": 1, "grid_y": 1, "threshold": 1.0})
    assert problem.metadata["payload_container_count_lower_bound"] == 2
    assert problem.metadata["container_count_lower_bound"] == 2


def test_level2_solver_audits_active_support_binaries():
    items = [Item("A", 10, 10, 5, 1), Item("B", 10, 10, 5, 1)]
    containers = [Container("C", 10, 10, 10, 10, 1, volume_m3=1e-6)]
    outcome = solve_level2(items, containers, {
        "time_limit_seconds": 10,
        "support": {"grid_x": 4, "grid_y": 4, "threshold": 0.8},
    })
    assert outcome.metadata["model_support_audit_valid"] is True
    assert outcome.metadata["model_support_audit_issue_count"] == 0
    assert outcome.metadata["mip_gap"] == pytest.approx(0.0)
    assert outcome.metadata["mip_dual_bound"] == pytest.approx(outcome.solve.objective_value)
    assert outcome.metadata["mip_node_count"] >= 0
