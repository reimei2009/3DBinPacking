import json
from pathlib import Path

import pytest
import yaml

from container_packing.data_loader import load_config
from container_packing.sweeps import run_parameter_sweep


def write_sweep(root: Path, tmp_path: Path, parameters: dict, *, max_sets: int = 10) -> Path:
    base = load_config(root / "config/level_01/default.yaml")
    base["paths"]["raw_items_csv"] = str(root / "data/raw/dataset_small_items_original.csv")
    base["paths"]["processed_dir"] = str(tmp_path / "processed/level_01")
    base["paths"]["manifest_json"] = str(tmp_path / "processed/level_01/latest_manifest.json")
    base["paths"]["output_root"] = str(tmp_path / "outputs")
    base_file = tmp_path / "base.yaml"
    base_file.write_text(yaml.safe_dump(base, sort_keys=False), encoding="utf-8")
    definition = {
        "project": {
            "level_id": "level_01",
            "algorithm_id": "extreme_point_simulated_annealing",
        },
        "base_config": str(base_file),
        "instance": {"item_counts": [1], "container_counts": [2]},
        "execution": {"environment": "local", "seeds": [7, 11], "repeats": 2},
        "sweep": {"max_parameter_sets": max_sets, "parameters": parameters},
    }
    path = tmp_path / "sweep.yaml"
    path.write_text(yaml.safe_dump(definition, sort_keys=False), encoding="utf-8")
    return path


def test_parameter_sweep_writes_ranked_isolated_outputs(root: Path, tmp_path: Path):
    path = write_sweep(root, tmp_path, {
        "max_iterations": [0, 2],
        "initial_temperature": [0.1],
    })
    result = run_parameter_sweep(path, project_root=root)

    assert result.successful
    assert "__level_01__parameter_sweep__extreme_point_simulated_annealing__" in result.sweep_id
    assert len(result.parameter_sets) == 2
    assert len(result.results) == 8
    assert len(result.summary) == 2
    assert set(result.ranking["rank"]) == {1, 2}
    assert result.results.groupby(["parameter_set_id", "random_seed"])["placement_signature"].nunique().eq(1).all()
    for name in (
        "request.json", "parameter_sets.csv", "results.csv", "summary.csv",
        "summary.json", "ranking.csv", "best_parameters.json",
    ):
        assert (result.run_dir / "sweep" / name).is_file()

    manifest = json.loads((result.run_dir / "manifest.json").read_text(encoding="utf-8"))
    best = json.loads((result.run_dir / "sweep/best_parameters.json").read_text(encoding="utf-8"))
    assert manifest["run_type"] == "parameter_sweep"
    assert manifest["level"] == "level_01"
    assert manifest["status"] == "SUCCESS"
    assert manifest["parameter_set_count"] == 2
    assert manifest["case_count"] == manifest["successful_case_count"] == 8
    assert manifest["random_seeds"] == [7, 11]
    assert len(best["rows"]) == 1

    parameter_map = result.parameter_sets.set_index("parameter_set_id").to_dict(orient="index")
    for row in result.results.itertuples():
        run_dir = Path(row.experiment_run_dir)
        resolved = yaml.safe_load((run_dir / "resolved_config.yaml").read_text(encoding="utf-8"))
        expected = parameter_map[row.parameter_set_id]
        assert resolved["project"]["random_seed"] == row.random_seed
        assert resolved["algorithms"]["extreme_point_simulated_annealing"]["max_iterations"] == expected["max_iterations"]
        assert resolved["algorithms"]["extreme_point_simulated_annealing"]["initial_temperature"] == expected["initial_temperature"]
        source_manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        assert source_manifest["validation_status"] == "VALID"


def test_parameter_sweep_rejects_unknown_and_excessive_grids(root: Path, tmp_path: Path):
    unknown = write_sweep(root, tmp_path, {"not_a_parameter": [1]})
    with pytest.raises(ValueError, match="Unknown algorithm parameters"):
        run_parameter_sweep(unknown, project_root=root)

    excessive = write_sweep(root, tmp_path, {
        "max_iterations": [1, 2], "initial_temperature": [0.1, 0.2],
    }, max_sets=3)
    with pytest.raises(ValueError, match="above max_parameter_sets"):
        run_parameter_sweep(excessive, project_root=root)


def test_parameter_sweep_supports_level_config_parameters(root: Path, tmp_path: Path):
    base = load_config(root / "config/level_02/default.yaml")
    base["paths"]["raw_items_csv"] = str(root / "data/raw/dataset_small_items_original.csv")
    base["paths"]["processed_dir"] = str(tmp_path / "processed/level_02")
    base["paths"]["manifest_json"] = str(tmp_path / "processed/level_02/latest_manifest.json")
    base["paths"]["output_root"] = str(tmp_path / "outputs")
    base_file = tmp_path / "level_02_base.yaml"
    base_file.write_text(yaml.safe_dump(base, sort_keys=False), encoding="utf-8")
    definition = {
        "project": {"level_id": "level_02", "algorithm_id": "extreme_point_ffd"},
        "base_config": str(base_file),
        "instance": {"item_counts": [1], "container_counts": [2]},
        "execution": {"environment": "local", "seeds": [7], "repeats": 1},
        "sweep": {
            "max_parameter_sets": 2,
            "config_parameters": {"support.threshold": [0.8, 0.9]},
        },
    }
    sweep_file = tmp_path / "level_02_support_sweep.yaml"
    sweep_file.write_text(yaml.safe_dump(definition, sort_keys=False), encoding="utf-8")

    result = run_parameter_sweep(sweep_file, project_root=root)

    assert result.successful
    assert set(result.parameter_sets["support.threshold"]) == {0.8, 0.9}
    assert set(result.results["support_threshold"]) == {0.8, 0.9}
    for row in result.results.itertuples():
        resolved = yaml.safe_load((Path(row.experiment_run_dir) / "resolved_config.yaml").read_text(encoding="utf-8"))
        assert resolved["support"]["threshold"] == row.support_threshold


def test_parameter_sweep_rejects_unknown_config_parameter(root: Path, tmp_path: Path):
    path = write_sweep(root, tmp_path, {"max_iterations": [1]})
    definition = yaml.safe_load(path.read_text(encoding="utf-8"))
    definition["sweep"]["config_parameters"] = {"paths.output_root": ["outputs"]}
    path.write_text(yaml.safe_dump(definition, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="must be under model, support, solver, or validation"):
        run_parameter_sweep(path, project_root=root)
