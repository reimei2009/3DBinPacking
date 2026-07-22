import json
from pathlib import Path

import pytest
import yaml

from container_packing.application.service import (
    build_experiment_request,
    discover_benchmark_runs,
    discover_runs,
    execute_benchmark_comparison,
    get_instance_limits,
)
from container_packing.data_loader import load_config


def test_web_application_boundary_builds_registry_validated_request(root):
    config = root / "config/level_01/default.yaml"
    limits = get_instance_limits(config, root=root)
    assert limits.available_items == 501
    assert limits.configured_containers == 5
    request = build_experiment_request(
        level_id="level_01", algorithm_id="extreme_point_ffd",
        item_count=30, container_count=7, random_seed=11,
        config_path=config, root=root,
    )
    assert request.item_count == 30
    assert request.container_count == 7
    assert request.random_seed == 11


def test_application_boundary_rejects_unavailable_item_count(root):
    with pytest.raises(ValueError, match="only 501"):
        build_experiment_request(
            level_id="level_01", algorithm_id="extreme_point_ffd",
            item_count=502, container_count=5,
            config_path=root / "config/level_01/default.yaml", root=root,
        )


def test_run_discovery_is_level_isolated(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    (tmp_path / "config").mkdir()
    first = tmp_path / "outputs/level_01/runs/run-1"
    first.mkdir(parents=True)
    (first / "metrics").mkdir()
    (first / "manifest.json").write_text(json.dumps({
        "run_id": "run-1", "level": "level_01", "algorithm": "milp_big_m",
        "status": "OPTIMAL", "validation_status": "VALID", "created_at_utc": "2026-01-01T00:00:00Z",
    }), encoding="utf-8")
    (first / "metrics/metrics.json").write_text(json.dumps({
        "n_items": 10, "n_containers_available": 3,
    }), encoding="utf-8")
    other = tmp_path / "outputs/level_02/runs/run-2"
    other.mkdir(parents=True)
    (other / "manifest.json").write_text("{}", encoding="utf-8")
    runs = discover_runs("level_01", root=tmp_path)
    assert len(runs) == 1
    assert runs[0].run_id == "run-1"
    assert runs[0].item_count == 10


def test_benchmark_discovery_requires_benchmark_artifacts(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    benchmark = tmp_path / "outputs/level_01/runs/benchmark-1"
    (benchmark / "benchmark").mkdir(parents=True)
    (benchmark / "manifest.json").write_text(json.dumps({
        "run_id": "benchmark-1",
        "run_type": "benchmark",
        "level": "level_01",
        "status": "SUCCESS",
        "created_at_utc": "2026-01-01T00:00:00Z",
        "case_count": 4,
        "successful_case_count": 4,
        "random_seeds": [7, 11],
        "repeats_per_seed": 2,
    }), encoding="utf-8")
    (benchmark / "benchmark/summary.csv").write_text("level,algorithm\nlevel_01,extreme_point_ffd\n", encoding="utf-8")
    (benchmark / "benchmark/results.csv").write_text("level,algorithm\nlevel_01,extreme_point_ffd\n", encoding="utf-8")
    incomplete = tmp_path / "outputs/level_01/runs/benchmark-incomplete"
    incomplete.mkdir(parents=True)
    (incomplete / "manifest.json").write_text(json.dumps({
        "run_id": "benchmark-incomplete", "run_type": "benchmark", "level": "level_01",
    }), encoding="utf-8")

    benchmarks = discover_benchmark_runs("level_01", root=tmp_path)

    assert len(benchmarks) == 1
    assert benchmarks[0].run_id == "benchmark-1"
    assert benchmarks[0].case_count == 4
    assert benchmarks[0].random_seeds == (7, 11)


def test_interactive_benchmark_uses_one_shared_instance(root: Path, tmp_path: Path):
    config = load_config(root / "config/level_01/default.yaml")
    config["paths"]["raw_items_csv"] = str(root / "data/raw/dataset_small_items_original.csv")
    config["paths"]["processed_dir"] = str(tmp_path / "processed/level_01")
    config["paths"]["manifest_json"] = str(tmp_path / "processed/level_01/latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / "outputs")
    config_path = tmp_path / "level_01.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    result = execute_benchmark_comparison(
        level_id="level_01",
        algorithm_ids=["extreme_point_ffd", "extreme_point_best_fit"],
        item_count=1,
        container_count=2,
        seeds=[7],
        repeats=1,
        config_path=config_path,
        root=root,
        item_selection_strategy="stable_random",
        item_selection_seed=101,
    )

    assert result.successful
    assert set(result.results["algorithm"]) == {"extreme_point_ffd", "extreme_point_best_fit"}
    assert set(result.results["scenario_id"]) == {"interactive_i1_c2"}
    assert result.results["input_fingerprint"].nunique() == 1
    assert set(result.results["item_selection_strategy"]) == {"stable_random"}


def test_interactive_benchmark_requires_two_algorithms(root: Path):
    with pytest.raises(ValueError, match="at least two algorithms"):
        execute_benchmark_comparison(
            level_id="level_01",
            algorithm_ids=["extreme_point_ffd"],
            item_count=1,
            container_count=1,
            seeds=[7],
            root=root,
        )
