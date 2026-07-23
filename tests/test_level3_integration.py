"""Registry-driven Level 3 FFD integration coverage."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
import pytest

from container_packing.data_loader import load_config
from container_packing.experiments.contracts import ExperimentRequest
from container_packing.experiments.runner import run_experiment


@pytest.mark.parametrize("algorithm_id", [
    "extreme_point_ffd", "extreme_point_best_fit", "extreme_point_hill_climbing",
    "extreme_point_simulated_annealing",
    "maximal_space_best_fit",
])
def test_level3_constructive_solver_writes_isolated_orientation_aware_run(
    root: Path, tmp_path: Path, algorithm_id: str,
) -> None:
    config = load_config(root / "config/level_03/default.yaml")
    config["paths"].update({
        "processed_dir": str(tmp_path / "processed" / "level_03"),
        "manifest_json": str(tmp_path / "processed" / "level_03" / "latest_manifest.json"),
        "output_root": str(tmp_path / "outputs"),
    })
    config_path = tmp_path / "level_03.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    result = run_experiment(ExperimentRequest("level_03", algorithm_id, config_path, 1, 2))

    assert result.solve.status == "FEASIBLE"
    assert result.validation is not None and result.validation.valid
    run_dir = Path(result.metadata["run_dir"])
    assert run_dir.parts[-4:-2] == ("outputs", "level_03")
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    metrics = json.loads((run_dir / "metrics" / "metrics.json").read_text(encoding="utf-8"))
    support = json.loads((run_dir / "validation" / "support_validation.json").read_text(encoding="utf-8"))
    assert manifest["level"] == "level_03"
    assert manifest["orientation_profile"] == "horizontal_rotatable"
    assert manifest["orientation_data_status"] == "synthetic_orientation_profile"
    assert metrics["orientation_profile"] == "horizontal_rotatable"
    assert support["orientation_profile"] == "horizontal_rotatable"
    assert (run_dir / "solution" / "support.csv").is_file()


def test_level3_milp_reference_writes_isolated_orientation_aware_run(root: Path, tmp_path: Path) -> None:
    config = load_config(root / "config/level_03/experiments/milp_big_m_reference.yaml")
    config["paths"].update({
        "processed_dir": str(tmp_path / "processed" / "level_03"),
        "manifest_json": str(tmp_path / "processed" / "level_03" / "latest_manifest.json"),
        "output_root": str(tmp_path / "outputs"),
    })
    config_path = tmp_path / "level_03_milp.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    result = run_experiment(ExperimentRequest("level_03", "milp_big_m", config_path, 1, 2))

    assert result.solve.status == "OPTIMAL"
    assert result.validation is not None and result.validation.valid
    run_dir = Path(result.metadata["run_dir"])
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["level"] == "level_03"
    assert manifest["algorithm_role"] == "exact_reference"
    assert manifest["orientation_profile"] == "horizontal_rotatable"
    assert (run_dir / "solution" / "support.csv").is_file()
