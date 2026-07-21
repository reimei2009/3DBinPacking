import pytest

from container_packing.models.level_01.milp_model import build_level1_model
from container_packing.levels.level_01_pipeline import run_from_config
from container_packing.schemas import Container, Item
from container_packing.algorithms.exact.milp_big_m import extract_placements, solve_milp
from container_packing.levels.level_01_validation import validate_solution
from container_packing.algorithms.heuristics.extreme_point_ffd import solve_level1 as solve_extreme_point_ffd


def test_reference_model_shape(level1_items, level1_containers):
    problem = build_level1_model(level1_items, level1_containers)
    assert problem.metadata["n_variables"] == 5865
    assert problem.metadata["n_constraints"] == 18475
    assert problem.constraints.A.format == "csr"


@pytest.mark.slow
def test_reference_instance_is_optimal(root):
    result = run_from_config(root / "config/level_01/default.yaml", write_outputs=False)
    assert result.solve.status == "OPTIMAL"
    assert result.validation and result.validation.valid
    assert len(result.placements) == 20
    assert result.metadata["container_count"] == 2
    assert result.metadata["selected_containers"] == ["C2", "C4"]
    assert result.metadata["total_container_cost"] == pytest.approx(1810)
    assert result.solve.objective_value == pytest.approx(10992)


def test_one_item_instance():
    items = [Item("A", 1, 1, 1, 1)]
    containers = [Container("C", 2, 2, 2, 2, 7, volume_m3=8e-9)]
    problem = build_level1_model(items, containers); result = solve_milp(problem, {"display": False})
    placements = extract_placements(result, problem, items, containers, tolerance=1e-4)
    assert result.status == "OPTIMAL"
    assert validate_solution(items, containers, placements).valid


def test_infeasible_instance_has_no_solution_vector():
    items = [Item("A", 1, 1, 1, 5)]
    containers = [Container("C", 2, 2, 2, 1, 7, volume_m3=8e-9)]
    result = solve_milp(build_level1_model(items, containers), {"display": False})
    assert result.status == "INFEASIBLE"
    assert result.vector is None


def test_reference_instance_extreme_point_baseline(level1_items, level1_containers):
    outcome = solve_extreme_point_ffd(level1_items, level1_containers)
    validation = validate_solution(level1_items, level1_containers, outcome.placements)
    assert outcome.solve.status == "FEASIBLE"
    assert validation.valid
    assert len(outcome.placements) == 20
    assert {value.container_id for value in outcome.placements} == {"C2", "C4"}
    assert outcome.solve.objective_value == pytest.approx(10992)
    assert outcome.metadata["optimality_proven"] is False
