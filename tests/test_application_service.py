import json
from pathlib import Path

import pytest
import yaml

from container_packing.application.service import (
    build_experiment_request,
    discover_benchmark_runs,
    discover_runs,
    execute_benchmark_comparison,
    get_benchmark_input_provenance,
    get_inventory_request_preview,
    get_instance_limits,
    resolve_active_data_context,
)
from container_packing.data_loader import load_config
from container_packing.benchmarks.legacy_audit import audit_level2_default_source_benchmarks


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


def test_application_boundary_uses_level7_algorithm_specific_fixture_config(root):
    request = build_experiment_request(
        level_id="level_07", algorithm_id="extreme_point_ffd_balance_fixture",
        item_count=3, container_count=1, root=root,
    )

    assert request.config_path == root / "config/level_07/experiments/ffd_balance_aware_fixture.yaml"


def test_application_boundary_rejects_unavailable_item_count(root):
    with pytest.raises(ValueError, match="only 501"):
        build_experiment_request(
            level_id="level_01", algorithm_id="extreme_point_ffd",
            item_count=502, container_count=5,
            config_path=root / "config/level_01/default.yaml", root=root,
        )


def test_inventory_request_preview_is_read_only_and_reports_lower_bounds(root):
    preview = get_inventory_request_preview(
        root / "config/level_01/default.yaml",
        item_count=20,
        initial_used_container_count=1,
        max_used_container_count=5,
        root=root,
    )

    assert preview.item_count == 20
    assert len(preview.selected_item_ids_checksum) == 64
    assert preview.total_item_volume_m3 > 0
    assert preview.total_item_weight_kg > 0
    assert preview.physical_container_count == 5
    assert preview.equivalent_type_count == 5
    assert preview.aggregate_lower_bound == max(
        preview.volume_lower_bound, preview.payload_lower_bound,
    )
    assert preview.recommended_max_used_container_count >= preview.aggregate_lower_bound
    assert preview.estimated_unique_composition_count > 0
    assert preview.capacity_limit_valid
    assert preview.volume_deficit_m3 == 0
    assert preview.payload_deficit_kg == 0


def test_inventory_request_preview_reports_proven_container_limit_deficit(root):
    preview = get_inventory_request_preview(
        root / "config/level_01/default.yaml",
        item_count=100,
        initial_used_container_count=1,
        max_used_container_count=1,
        root=root,
    )

    assert not preview.capacity_limit_valid
    assert preview.aggregate_lower_bound > 1
    assert preview.volume_deficit_m3 > 0 or preview.payload_deficit_kg > 0


def test_generated_level2_benchmark_preview_uses_qualified_profile_and_capacity_gate(root):
    config = root / "config/level_02/experiments/inventory_items_1000_fleet_500.yaml"
    provenance = get_benchmark_input_provenance(config, root=root)
    assert provenance.dataset_profile_id == "level_02_inventory_items_1000_fleet_500_t10_v1"
    assert provenance.available_item_count == 1000
    assert provenance.physical_container_count == 500
    assert provenance.raw_items_checksum != (
        "33cc4d74b04c34714f1c3ed639396deda5c087a408214f6541d744142b239a1e"
    )

    blocked = get_inventory_request_preview(
        config, item_count=500, initial_used_container_count=10,
        max_used_container_count=10, root=root,
    )
    assert blocked.aggregate_lower_bound == 14
    assert not blocked.capacity_limit_valid
    assert blocked.payload_deficit_kg > 36_000

    for maximum in (20, 50):
        allowed = get_inventory_request_preview(
            config, item_count=500, initial_used_container_count=14,
            max_used_container_count=maximum, root=root,
        )
        assert allowed.aggregate_lower_bound == 14
        assert allowed.capacity_limit_valid


def test_level2_active_data_context_is_the_generated_solver_source(root):
    context = resolve_active_data_context(
        "level_02",
        root / "config/level_02/experiments/inventory_items_1000_fleet_500.yaml",
        root=root,
    )

    assert context.level_id == "level_02"
    assert context.profile_id == "level_02_inventory_items_1000_fleet_500_t10_v1"
    assert context.available_item_count == 1000
    assert context.physical_container_count == 500
    assert context.solver_acceptance_allowed
    assert context.raw_items_checksum != (
        "33cc4d74b04c34714f1c3ed639396deda5c087a408214f6541d744142b239a1e"
    )


def test_level3_active_data_context_reuses_the_qualified_inventory_source(root):
    config = root / "config/level_03/experiments/inventory_items_1000_fleet_500.yaml"
    context = resolve_active_data_context("level_03", config, root=root)
    provenance = get_benchmark_input_provenance(config, root=root)

    assert context.level_id == "level_03"
    assert context.profile_id == "level_02_inventory_items_1000_fleet_500_t10_v1"
    assert context.available_item_count == 1000
    assert context.physical_container_count == 500
    assert context.solver_acceptance_allowed
    assert provenance.dataset_profile_id == context.profile_id
    assert provenance.raw_items_checksum == context.raw_items_checksum
    assert provenance.container_catalog_checksum == context.container_catalog_checksum


@pytest.mark.parametrize("level_id", ["level_04", "level_05"])
def test_level4_5_active_data_context_reuses_qualified_inventory_source(
    root: Path, level_id: str,
) -> None:
    config = root / f"config/{level_id}/experiments/inventory_items_1000_fleet_500.yaml"
    context = resolve_active_data_context(level_id, config, root=root)
    provenance = get_benchmark_input_provenance(config, root=root)
    level3 = resolve_active_data_context(
        "level_03",
        root / "config/level_03/experiments/inventory_items_1000_fleet_500.yaml",
        root=root,
    )

    assert context.level_id == level_id
    assert context.profile_id == "level_02_inventory_items_1000_fleet_500_t10_v1"
    assert context.available_item_count == 1000
    assert context.physical_container_count == 500
    assert context.solver_acceptance_allowed
    assert context.raw_items_checksum == level3.raw_items_checksum
    assert context.container_catalog_checksum == level3.container_catalog_checksum
    assert provenance.dataset_profile_id == context.profile_id
    assert provenance.raw_items_checksum == context.raw_items_checksum
    assert provenance.container_catalog_checksum == context.container_catalog_checksum


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
    assert benchmarks[0].execution_count == 4
    assert benchmarks[0].successful_execution_count == 4
    assert benchmarks[0].random_seeds == (7, 11)


def test_benchmark_discovery_filters_to_the_active_profile(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    for run_id, config_file, profile in (
        ("generated", str(tmp_path / "generated.yaml"), "generated_1k"),
        ("default", str(tmp_path / "default.yaml"), None),
    ):
        run_dir = tmp_path / "outputs/level_02/runs" / run_id
        (run_dir / "benchmark").mkdir(parents=True)
        (run_dir / "benchmark/summary.csv").write_text("algorithm\nextreme_point_ffd\n", encoding="utf-8")
        (run_dir / "benchmark/results.csv").write_text("algorithm\nextreme_point_ffd\n", encoding="utf-8")
        (run_dir / "manifest.json").write_text(json.dumps({
            "run_id": run_id, "run_type": "benchmark", "level": "level_02",
            "status": "SUCCESS", "created_at_utc": "2026-01-01T00:00:00Z",
            "case_count": 1, "successful_case_count": 1, "random_seeds": [42],
            "config_file": config_file,
            "dataset_usage": {"profile_id": profile} if profile else None,
            "dataset_provenance": {"raw_items_checksum": run_id, "container_catalog_checksum": "catalog"},
        }), encoding="utf-8")
    selected = discover_benchmark_runs(
        "level_02", root=tmp_path, config_file=tmp_path / "generated.yaml",
        dataset_profile_id="generated_1k",
        expected_raw_items_checksum="generated",
        expected_container_catalog_checksum="catalog",
    )
    assert [artifact.run_id for artifact in selected] == ["generated"]
    assert selected[0].raw_items_checksum == "generated"
    assert selected[0].container_catalog_checksum == "catalog"


def test_legacy_audit_is_read_only_and_selects_only_default_interactive_runs(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    source = tmp_path / "outputs/level_02/runs/source"
    source.mkdir(parents=True)
    (source / "payload.txt").write_text("source", encoding="utf-8")
    candidate = tmp_path / "outputs/level_02/runs/candidate"
    (candidate / "benchmark").mkdir(parents=True)
    (candidate / "manifest.json").write_text(json.dumps({
        "run_id": "candidate", "run_type": "benchmark", "level": "level_02",
        "suite_id": "level_02_interactive_comparison",
        "config_file": str(tmp_path / "config/level_02/default.yaml"),
        "source_runs": [str(source)],
    }), encoding="utf-8")
    unrelated = tmp_path / "outputs/level_02/runs/generated"
    unrelated.mkdir(parents=True)
    (unrelated / "manifest.json").write_text(json.dumps({
        "run_type": "benchmark", "level": "level_02",
        "suite_id": "other", "config_file": "config/level_02/default.yaml",
    }), encoding="utf-8")
    benchmarks, sources = audit_level2_default_source_benchmarks(tmp_path)
    assert benchmarks.benchmark_run_id.tolist() == ["candidate"]
    assert sources.source_run_dir.tolist() == [str(source.resolve())]
    assert benchmarks.iloc[0].recommended_action == "review_then_delete"
    assert benchmarks.iloc[0].can_regenerate
    assert sources.iloc[0].recommended_action == "retain_until_reference_audit"
    assert sources.iloc[0].referenced_by_benchmark_ids == ["candidate"]
    assert (source / "payload.txt").read_text(encoding="utf-8") == "source"


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
    for filename in ("case_features.csv", "pairwise_outcomes.csv", "distribution_summary.csv"):
        assert (result.run_dir / "benchmark" / filename).is_file()


def test_level2_generated_interactive_benchmark_persists_the_active_source(
    root: Path, tmp_path: Path,
) -> None:
    config = load_config(
        root / "config/level_02/experiments/inventory_items_1000_fleet_500.yaml"
    )
    config["paths"]["processed_dir"] = str(tmp_path / "processed/level_02")
    config["paths"]["manifest_json"] = str(
        tmp_path / "processed/level_02/latest_manifest.json"
    )
    config["paths"]["output_root"] = str(tmp_path / "outputs")
    config_path = tmp_path / "level_02_generated.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    context = resolve_active_data_context("level_02", config_path, root=root)

    result = execute_benchmark_comparison(
        level_id="level_02",
        algorithm_ids=["extreme_point_ffd", "extreme_point_best_fit"],
        item_count=1,
        container_count=1,
        seeds=[7],
        repeats=1,
        config_path=config_path,
        root=root,
        config_overrides={
            "container_search": {
                "enabled": True,
                "initial_used_container_count": 1,
                "max_used_container_count": 1,
                "time_limit_seconds": 10,
                "validation_reserve_seconds": 2,
                "consolidation": {"enabled": False},
            },
        },
    )

    manifest = json.loads((result.run_dir / "manifest.json").read_text(encoding="utf-8"))
    request = json.loads(
        (result.run_dir / "benchmark/request.json").read_text(encoding="utf-8")
    )
    provenance = manifest["dataset_provenance"]
    assert result.successful
    assert request["config_file"] == str(config_path.resolve())
    assert request["scenarios"][0]["item_count"] == 1
    assert request["scenarios"][0]["container_count"] == 1
    assert request["config_overrides"]["container_search"]["max_used_container_count"] == 1
    assert provenance["raw_items_checksum"] == context.raw_items_checksum
    assert provenance["container_catalog_checksum"] == context.container_catalog_checksum
    assert result.results["input_fingerprint"].nunique() == 1


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
