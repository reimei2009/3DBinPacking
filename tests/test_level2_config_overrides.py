import yaml
import json

from container_packing.application.service import (
    build_experiment_request,
    execute_benchmark_comparison,
    execute_experiment,
    resolve_result_run_dir,
)


def test_level2_support_threshold_override_is_persisted(root):
    request = build_experiment_request(
        level_id="level_02",
        algorithm_id="extreme_point_ffd",
        item_count=3,
        container_count=2,
        config_path=root / "config/level_02/default.yaml",
        config_overrides={"support": {"threshold": 0.9}},
        root=root,
    )
    result = execute_experiment(request)
    run_dir = resolve_result_run_dir(result, root=root)
    resolved = yaml.safe_load((run_dir / "resolved_config.yaml").read_text(encoding="utf-8"))
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))

    assert result.validation is not None and result.validation.valid
    assert resolved["support"]["threshold"] == 0.9
    assert result.metadata["support_threshold"] == 0.9
    assert result.metadata["config_overrides"] == {"support": {"threshold": 0.9}}
    assert manifest["support_threshold"] == 0.9
    assert manifest["config_overrides"] == {"support": {"threshold": 0.9}}


def test_level2_benchmark_applies_one_support_threshold_to_every_algorithm(root):
    result = execute_benchmark_comparison(
        level_id="level_02",
        algorithm_ids=("extreme_point_ffd", "extreme_point_best_fit"),
        item_count=1,
        container_count=2,
        seeds=(7,),
        config_path=root / "config/level_02/default.yaml",
        config_overrides={"support": {"threshold": 0.9}},
        root=root,
    )
    resolved = yaml.safe_load((result.run_dir / "resolved_config.yaml").read_text(encoding="utf-8"))
    request = json.loads((result.run_dir / "benchmark/request.json").read_text(encoding="utf-8"))

    assert result.successful
    assert resolved["support"]["threshold"] == 0.9
    assert request["config_overrides"] == {"support": {"threshold": 0.9}}
    assert set(result.results["support_threshold"]) == {0.9}


def test_level2_generated_inventory_benchmark_preserves_generated_provenance(root):
    result = execute_benchmark_comparison(
        level_id="level_02",
        algorithm_ids=("extreme_point_ffd", "extreme_point_best_fit"),
        item_count=1,
        container_count=1,
        seeds=(7,),
        config_path=root / "config/level_02/experiments/inventory_items_1000_fleet_500.yaml",
        config_overrides={
            "container_search": {
                "enabled": True,
                "initial_used_container_count": 1,
                "max_used_container_count": 1,
                "automatically_increase_container_count": False,
                "time_limit_seconds": 60,
            },
        },
        root=root,
    )
    manifest = json.loads((result.run_dir / "manifest.json").read_text(encoding="utf-8"))
    request = json.loads((result.run_dir / "benchmark/request.json").read_text(encoding="utf-8"))
    assert result.successful
    assert manifest["dataset_usage"]["profile_id"] == "level_02_inventory_items_1000_fleet_500_t10_v1"
    assert manifest["dataset_provenance"]["raw_items_checksum"] != "33cc4d74b04c34714f1c3ed639396deda5c087a408214f6541d744142b239a1e"
    assert request["scenarios"][0]["selected_item_ids_checksum"]
    assert result.results["selected_item_ids_checksum"].nunique() == 1
