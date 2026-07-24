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
def test_level4_constructive_solver_writes_isolated_stackability_aware_run(
    root: Path, tmp_path: Path, algorithm_id: str,
) -> None:
    config = load_config(root / "config/level_04/default.yaml")
    config["paths"].update({
        "processed_dir": str(tmp_path / "processed" / "level_04"),
        "manifest_json": str(tmp_path / "processed" / "level_04" / "latest_manifest.json"),
        "output_root": str(tmp_path / "outputs"),
    })
    config_path = tmp_path / "level_04.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    result = run_experiment(ExperimentRequest("level_04", algorithm_id, config_path, 2, 1))

    assert result.solve.status == "FEASIBLE"
    assert result.validation is not None and result.validation.valid
    run_dir = Path(result.metadata["run_dir"])
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    solution = json.loads((run_dir / "solution" / "solution.json").read_text(encoding="utf-8"))
    metrics = json.loads((run_dir / "metrics" / "metrics.json").read_text(encoding="utf-8"))
    assert manifest["level"] == "level_04"
    assert manifest["orientation_profile"] == "horizontal_rotatable"
    assert manifest["stackability_contract_version"] == 1
    assert solution["stackability"]["stack_count"] >= 1
    assert metrics["stackability_enabled"] is True
    assert (run_dir / "solution" / "stacks.csv").is_file()
    assert (run_dir / "validation" / "stack_validation.json").is_file()
    if algorithm_id in {"extreme_point_hill_climbing", "extreme_point_simulated_annealing"}:
        solver = json.loads((run_dir / "solver" / "solver_summary.json").read_text(encoding="utf-8"))
        expected_role = (
            "local_search_comparator" if algorithm_id == "extreme_point_hill_climbing"
            else "metaheuristic_comparator"
        )
        assert manifest["algorithm_role"] == expected_role
        assert solver["initial_constructor"] == "extreme_point_best_fit"
        assert solver["repair_constructor"] == "extreme_point_best_fit"
    if algorithm_id == "extreme_point_simulated_annealing":
        resolved = yaml.safe_load((run_dir / "resolved_config.yaml").read_text(encoding="utf-8"))
        sa = resolved["algorithms"]["extreme_point_simulated_annealing"]
        assert sa["max_iterations"] == 200
        assert sa["initial_temperature"] == 0.05
        assert sa["cooling_rate"] == 0.99
