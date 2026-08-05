from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest
import yaml

from container_packing.benchmarks import run_benchmark
from container_packing.benchmarks.runner import _input_fingerprint
from container_packing.benchmarks.suites import BenchmarkScenario
from container_packing.data_loader import load_config
from container_packing.dataset_usage import DatasetExecutionIntent, validate_dataset_usage
from container_packing.experiments.contracts import ExperimentRequest
from container_packing.experiments.runner import run_experiment
from container_packing.instance_data import prepare_instance
from container_packing.synthetic_instances import (
    generate_large_synthetic_instances,
    load_large_synthetic_profile,
)


def _generated(root: Path, output: Path, *, usage_class: str = "solver_research") -> dict:
    base = load_large_synthetic_profile(root / "config/synthetic/scale_1k_100.yaml", root=root)
    profile = replace(
        base,
        item_count=12,
        delivery_stop_count=3,
        container_quantities={"C1": 0, "C2": 0, "C3": 0, "C4": 0, "C5": 2},
        usage_class=usage_class,
        minimum_volume_margin_ratio=1.4 if usage_class == "solver_research" else 1.0,
        minimum_payload_margin_ratio=1.4 if usage_class == "solver_research" else 1.0,
        output_dir=output,
    )
    return generate_large_synthetic_instances(profile)


def _config(root: Path, tmp_path: Path, generated: dict, *, usage_class: str) -> dict:
    config = load_config(root / "config/level_08/default.yaml")
    config["instance"] = {
        "item_count": 12, "container_count": 2,
        "item_selection_strategy": "prefix", "item_selection_seed": None,
    }
    config["paths"].update({
        "raw_items_csv": generated["solver_items_path"],
        "raw_containers_csv": generated["solver_containers_path"],
        "items_source_mapping": str(root / "config/common/data_sources/empirical_template_level_08.yaml"),
        "processed_dir": str(tmp_path / "processed"),
        "manifest_json": str(tmp_path / "processed/latest.json"),
        "output_root": str(tmp_path / "outputs"),
    })
    config["dataset_policy"] = {
        "generation_manifest": generated["manifest_path"],
        "expected_usage_class": usage_class,
    }
    return config


def _write_config(tmp_path: Path, config: dict) -> Path:
    path = tmp_path / "experiment.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def test_raw_dataset_without_policy_is_unchanged(root: Path) -> None:
    config = load_config(root / "config/level_01/default.yaml")
    assert validate_dataset_usage(root, config, DatasetExecutionIntent.SOLVER_EXPERIMENT) is None


def test_solver_qualified_dataset_is_allowed_for_all_intents(root: Path, tmp_path: Path) -> None:
    generated = _generated(root, tmp_path / "generated")
    config = _config(root, tmp_path, generated, usage_class="solver_research")

    for intent in DatasetExecutionIntent:
        evidence = validate_dataset_usage(root, config, intent)
        assert evidence is not None
        assert evidence.profile_id == generated["profile_id"]
        assert evidence.capacity_qualification == "solver_qualified"
        assert evidence.solver_acceptance_allowed
        assert evidence.execution_intent == intent.value


def test_pipeline_only_prepares_and_snapshots_evidence(root: Path, tmp_path: Path) -> None:
    generated = _generated(root, tmp_path / "generated", usage_class="data_pipeline_only")
    config = _config(root, tmp_path, generated, usage_class="data_pipeline_only")

    evidence = validate_dataset_usage(root, config, DatasetExecutionIntent.DATA_PREPARATION)
    manifest = prepare_instance(root, config, level_id="level_08")

    assert evidence is not None
    assert evidence.capacity_qualification == "pipeline_qualified"
    assert manifest["dataset_usage"]["usage_class"] == "data_pipeline_only"
    assert manifest["dataset_usage"]["execution_intent"] == "data_preparation"


@pytest.mark.parametrize(
    "intent", [DatasetExecutionIntent.SOLVER_EXPERIMENT, DatasetExecutionIntent.BENCHMARK_ACCEPTANCE],
)
def test_pipeline_only_is_rejected_for_solver_intents(
    root: Path, tmp_path: Path, intent: DatasetExecutionIntent,
) -> None:
    generated = _generated(root, tmp_path / intent.value, usage_class="data_pipeline_only")
    config = _config(root, tmp_path / intent.value, generated, usage_class="data_pipeline_only")

    with pytest.raises(ValueError, match="cannot be used for"):
        validate_dataset_usage(root, config, intent)


def test_experiment_rejects_pipeline_only_before_level_execution(root: Path, tmp_path: Path) -> None:
    generated = _generated(root, tmp_path / "generated", usage_class="data_pipeline_only")
    config = _config(root, tmp_path, generated, usage_class="data_pipeline_only")
    request = ExperimentRequest(
        level_id="level_08", algorithm_id="extreme_point_best_fit_delivery",
        config_path=_write_config(tmp_path, config), item_count=12, container_count=2,
        environment="local", random_seed=42,
    )

    with pytest.raises(ValueError, match="Allowed intent: data_preparation"):
        run_experiment(request)
    assert not (tmp_path / "outputs").exists()


def test_solver_experiment_snapshots_usage_evidence_in_run_manifest(root: Path, tmp_path: Path) -> None:
    generated = _generated(root, tmp_path / "generated")
    config = _config(root, tmp_path, generated, usage_class="solver_research")
    request = ExperimentRequest(
        level_id="level_08", algorithm_id="extreme_point_best_fit_delivery",
        config_path=_write_config(tmp_path, config), item_count=3, container_count=2,
        environment="local", random_seed=42,
    )

    result = run_experiment(request)
    run_manifest = json.loads((Path(result.metadata["run_dir"]) / "manifest.json").read_text(encoding="utf-8"))

    assert run_manifest["dataset_usage"]["usage_class"] == "solver_research"
    assert run_manifest["dataset_usage"]["execution_intent"] == "solver_experiment"


def test_benchmark_rejects_pipeline_only_before_creating_output(root: Path, tmp_path: Path) -> None:
    generated = _generated(root, tmp_path / "generated", usage_class="data_pipeline_only")
    config = _config(root, tmp_path, generated, usage_class="data_pipeline_only")
    config_path = _write_config(tmp_path, config)

    with pytest.raises(ValueError, match="benchmark_acceptance"):
        run_benchmark(
            level_id="level_08", algorithm_ids=["extreme_point_best_fit_delivery"],
            item_counts=[3], container_counts=[2], config_path=config_path,
            project_root=root,
        )
    assert not (tmp_path / "outputs").exists()


def test_checksum_tampering_and_profile_mismatch_are_rejected(root: Path, tmp_path: Path) -> None:
    first = _generated(root, tmp_path / "first")
    second = _generated(root, tmp_path / "second")
    mismatch = _config(root, tmp_path, first, usage_class="solver_research")
    mismatch["dataset_policy"]["generation_manifest"] = second["manifest_path"]
    with pytest.raises(ValueError, match="does not match generation manifest"):
        validate_dataset_usage(root, mismatch, DatasetExecutionIntent.DATA_PREPARATION)

    config = _config(root, tmp_path, first, usage_class="solver_research")
    items_path = Path(first["solver_items_path"])
    items_path.write_text(items_path.read_text(encoding="utf-8-sig") + "\n", encoding="utf-8-sig")
    with pytest.raises(ValueError, match="checksum mismatch"):
        validate_dataset_usage(root, config, DatasetExecutionIntent.DATA_PREPARATION)


def test_generated_path_without_policy_fails_actionably(root: Path) -> None:
    config = load_config(root / "config/level_08/default.yaml")
    config["paths"]["raw_items_csv"] = "data/interim/synthetic/missing/solver_items.csv"
    config["paths"]["raw_containers_csv"] = "data/interim/synthetic/missing/solver_containers.csv"

    with pytest.raises(ValueError, match="Generated datasets require dataset_policy"):
        validate_dataset_usage(root, config, DatasetExecutionIntent.DATA_PREPARATION)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("invalid_json", "Invalid JSON generation manifest"),
        ("unsupported_schema", "Unsupported generated dataset schema_version"),
        ("usage_mismatch", "Generated dataset usage mismatch"),
    ],
)
def test_invalid_manifest_and_expected_usage_are_rejected(
    root: Path, tmp_path: Path, mutation: str, message: str,
) -> None:
    generated = _generated(root, tmp_path / mutation)
    config = _config(root, tmp_path / mutation, generated, usage_class="solver_research")
    manifest_path = Path(generated["manifest_path"])
    if mutation == "invalid_json":
        manifest_path.write_text("{", encoding="utf-8")
    elif mutation == "unsupported_schema":
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["schema_version"] = "999"
        manifest_path.write_text(json.dumps(payload), encoding="utf-8")
    else:
        config["dataset_policy"]["expected_usage_class"] = "data_pipeline_only"

    with pytest.raises(ValueError, match=message):
        validate_dataset_usage(root, config, DatasetExecutionIntent.DATA_PREPARATION)


def test_generation_manifest_checksum_participates_in_benchmark_fingerprint(root: Path, tmp_path: Path) -> None:
    generated = _generated(root, tmp_path / "generated")
    config = _config(root, tmp_path, generated, usage_class="solver_research")
    evidence = validate_dataset_usage(root, config, DatasetExecutionIntent.BENCHMARK_ACCEPTANCE)
    assert evidence is not None
    scenario = BenchmarkScenario("fixture", "fixture", 3, 2)
    first = _input_fingerprint(level_id="level_08", scenario=scenario, config=config, root=root,
                               dataset_usage=evidence)
    second = _input_fingerprint(level_id="level_08", scenario=scenario, config=config, root=root,
                                dataset_usage=replace(evidence, generation_manifest_checksum="different"))

    assert first != second
