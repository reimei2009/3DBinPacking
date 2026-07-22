import json
from pathlib import Path

import pytest
import yaml

from container_packing.data_loader import load_config
from container_packing.experiments.contracts import ExperimentRequest
from container_packing.experiments.runner import run_experiment


def test_level2_run_is_isolated_and_writes_support_artifacts(root: Path, tmp_path: Path):
    config = load_config(root / "config/level_02/default.yaml")
    config["paths"]["raw_items_csv"] = str(root / "data/raw/dataset_small_items_original.csv")
    config["paths"]["processed_dir"] = str(tmp_path / "processed/level_02")
    config["paths"]["manifest_json"] = str(tmp_path / "processed/level_02/latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / "outputs")
    config_path = tmp_path / "level_02.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    result = run_experiment(ExperimentRequest("level_02", "milp_big_m", config_path, 2, 2))
    run_dir = Path(result.metadata["run_dir"])
    if not run_dir.is_absolute():
        run_dir = root / run_dir
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    solver = json.loads((run_dir / "solver/solver_summary.json").read_text(encoding="utf-8"))
    assert result.validation and result.validation.valid
    assert run_dir.is_relative_to(tmp_path / "outputs/level_02/runs")
    assert not (tmp_path / "outputs/level_01").exists()
    assert (run_dir / "solution/support.csv").is_file()
    assert (run_dir / "validation/support_validation.json").is_file()
    assert manifest["level"] == "level_02"
    assert "support_grid_coverage" in manifest["active_constraints"]
    assert "aggregate_volume_capacity" in manifest["active_constraints"]
    assert "physical_stability" in manifest["inactive_constraints"]
    assert solver["capacity_strengthening_enabled"] is True
    assert solver["capacity_strengthening_cut_count"] == 5
    assert solver["mip_gap"] == 0.0
    assert result.metadata["algorithm_role"] == "exact_reference"
    assert solver["algorithm_role"] == "exact_reference"


@pytest.mark.parametrize("algorithm_id", [
    "extreme_point_ffd",
    "extreme_point_best_fit",
    "extreme_point_hill_climbing",
    "extreme_point_simulated_annealing",
    "maximal_space_best_fit",
])
def test_level2_heuristic_runs_are_valid_and_isolated(root: Path, tmp_path: Path, algorithm_id: str):
    case_root = tmp_path / algorithm_id
    config = load_config(root / "config/level_02/default.yaml")
    config["paths"]["raw_items_csv"] = str(root / "data/raw/dataset_small_items_original.csv")
    config["paths"]["processed_dir"] = str(case_root / "processed/level_02")
    config["paths"]["manifest_json"] = str(case_root / "processed/level_02/latest_manifest.json")
    config["paths"]["output_root"] = str(case_root / "outputs")
    config_path = case_root / "level_02.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    result = run_experiment(ExperimentRequest(
        "level_02", algorithm_id, config_path, 2, 2,
        algorithm_parameters={
            "max_iterations": 3, "max_neighbors": 6, "neighbors_per_iteration": 2,
        },
    ))
    run_dir = Path(result.metadata["run_dir"])
    if not run_dir.is_absolute():
        run_dir = root / run_dir
    solver = json.loads((run_dir / "solver/solver_summary.json").read_text(encoding="utf-8"))
    assert result.validation and result.validation.valid
    assert run_dir.is_relative_to(case_root / "outputs/level_02/runs")
    assert not (case_root / "outputs/level_01").exists()
    assert (run_dir / "solution/support.csv").is_file()
    assert solver["feasibility_policy"].endswith("exact_support")
    assert solver["heuristic_support_threshold"] == 0.8
    expected_role = "practical_default" if algorithm_id == "extreme_point_ffd" else "alternative_method"
    assert result.metadata["algorithm_role"] == expected_role
    assert solver["algorithm_role"] == expected_role
