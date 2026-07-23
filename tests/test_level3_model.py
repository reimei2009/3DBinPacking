import pytest

from container_packing.algorithms.exact.milp_big_m import solve_level3, solve_milp
from container_packing.levels.level_03_algorithms import execute_level_03
from container_packing.levels.level_03_validation import validate_solution
from container_packing.models.level_03.milp_model import build_level3_model
from container_packing.models.level_03.model_indices import Level03ModelIndices
from container_packing.schemas import Container, Item


def test_level3_indices_append_two_orientation_choices_per_item():
    indices = Level03ModelIndices(2, 1, 2, 2)
    values = set(range(indices.base.n_variables))
    values |= {indices.orientation(i, code) for i in range(2) for code in (0, 1)}
    assert values == set(range(indices.n_variables))


def test_level3_milp_selects_required_horizontal_rotation_and_validates():
    items = [Item("A", 12, 8, 5, 1)]
    containers = [Container("C", 8, 12, 5, 10, 1)]
    outcome = solve_level3(items, containers, {
        "time_limit_seconds": 10,
        "support": {"grid_x": 2, "grid_y": 2, "threshold": 0.8},
    })
    checked = validate_solution(items, containers, outcome.placements)
    assert outcome.solve.status == "OPTIMAL"
    assert checked.result.valid
    assert outcome.placements[0].orientation_code == "YXZ"
    assert outcome.placements[0].length_mm == 8
    assert outcome.placements[0].width_mm == 12
    assert outcome.metadata["orientation_variable_count"] == 2
    assert outcome.metadata["model_support_audit_valid"] is True


def test_level3_milp_stacked_solution_has_exact_support():
    items = [Item("A", 12, 8, 5, 1), Item("B", 12, 8, 5, 1)]
    containers = [Container("C", 8, 12, 10, 10, 1)]
    outcome = solve_level3(items, containers, {
        "time_limit_seconds": 10,
        "support": {"grid_x": 2, "grid_y": 2, "threshold": 1.0},
    })
    checked = validate_solution(items, containers, outcome.placements, support_threshold=1.0)
    assert outcome.solve.status == "OPTIMAL"
    assert checked.result.valid
    assert {placement.orientation_code for placement in outcome.placements} == {"YXZ"}
    assert sorted(value.z_mm for value in outcome.placements) == pytest.approx([0, 5])
    assert sorted(record.exact_support_ratio for record in checked.support_records) == [1, 1]


def test_level3_milp_reference_guard_rejects_practical_size():
    items = [Item(f"I{i}", 1, 1, 1, 1) for i in range(6)]
    containers = [Container("C", 10, 10, 10, 10, 1)]
    with pytest.raises(ValueError, match="exact reference limited to 5 items"):
        execute_level_03("milp_big_m", items, containers, {"support": {}})


def test_level3_milp_metadata_records_sparse_model_shape():
    items = [Item("A", 5, 4, 3, 1)]
    containers = [Container("C", 5, 4, 3, 10, 1)]
    problem = build_level3_model(items, containers, {"grid_x": 2, "grid_y": 2, "threshold": 0.8})
    solved = solve_milp(problem, {"time_limit_seconds": 10})
    assert solved.status == "OPTIMAL"
    assert problem.metadata["orientation_codes"] == ["XYZ", "YXZ"]
    assert problem.metadata["orientation_reference_max_items"] == 5
