from __future__ import annotations

from pathlib import Path

import pytest

from container_packing.application.failure_explanation import explain_failure
from container_packing.benchmarks.runner import execute_experiment_case
from container_packing.data_loader import load_config
from container_packing.experiments.contracts import ExperimentRequest
from container_packing.levels.level_01_pipeline import run_from_config
from container_packing.reporting import metrics_payload
from container_packing.runtime.failure_evidence import (
    ExperimentExecutionError,
    canonical_termination_reason,
    failure_metadata,
)


def test_failure_metadata_preserves_diagnostics_and_nulls_quality() -> None:
    error = OSError("locked output")

    value = failure_metadata({
        "status": "TIME_LIMIT",
        "objective_value": 1234.0,
        "official_objective": {"used_container_count": 2, "total_container_cost": 1000},
        "inventory_search_termination_reason": "time_limit_reached",
        "best_partial_placement_count": 99,
        "n_items": 100,
        "n_containers": 500,
    }, stage="reporting", error=error, failure_class="OUTPUT_PUBLICATION_FAILED")

    assert value["status"] == "ERROR"
    assert value["computation_status_before_failure"] == "TIME_LIMIT"
    assert value["candidate_objective_value"] == 1234.0
    assert value["objective_value"] is None
    assert value["official_objective"] is None
    assert value["search_termination_reason"] == "time_limit_reached"
    assert value["best_partial_placement_count"] == 99
    assert value["error_type"] == "OSError"


def test_metrics_payload_reports_missing_counts_without_raising() -> None:
    value = metrics_payload({
        "level_id": "level_05",
        "algorithm_id": "extreme_point_ffd",
        "status": "ERROR",
    }, False)

    assert value["n_items"] is None
    assert value["n_containers_available"] is None
    assert value["failure_evidence_complete"] is False
    assert value["failure_evidence_missing_fields"] == ["n_items", "n_containers"]


def test_canonical_termination_reason_uses_shared_precedence() -> None:
    metadata = {
        "construction_termination_reason": "time_limit_reached",
        "inventory_search_termination_reason": "search_time_limit",
    }

    assert canonical_termination_reason(metadata) == "search_time_limit"


def test_pipeline_always_publishes_resolved_input_counts(root: Path) -> None:
    result = run_from_config(
        root / "config/level_01/default.yaml",
        item_count=1,
        container_count=1,
        write_outputs=False,
        algorithm_id="extreme_point_ffd",
    )

    assert result.metadata["n_items"] == 1
    assert result.metadata["n_containers"] == 1
    assert result.metadata["requested_item_count"] == 1
    assert result.metadata["requested_container_count"] == 1


def _request(root: Path, config_path: Path | None = None) -> ExperimentRequest:
    return ExperimentRequest(
        level_id="level_01",
        algorithm_id="extreme_point_ffd",
        config_path=config_path or root / "config/level_01/default.yaml",
        item_count=1,
        container_count=1,
        random_seed=42,
    )


def test_benchmark_keeps_context_when_output_publication_fails(
    root: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import yaml
    import container_packing.levels.pipeline as pipeline

    config = load_config(root / "config/level_01/default.yaml")
    config["paths"].update({
        "raw_items_csv": str(root / "data/raw/dataset_small_items_original.csv"),
        "items_source_mapping": str(
            root / "config/common/data_sources/3dbppsi_dataset_small.yaml"
        ),
        "processed_dir": str(tmp_path / "processed"),
        "manifest_json": str(tmp_path / "processed/latest_manifest.json"),
        "output_root": str(tmp_path / "outputs"),
    })
    config_path = tmp_path / "level_01.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    def fail_output(*_args, **_kwargs):
        raise KeyError("n_items")

    monkeypatch.setattr(pipeline, "write_run_outputs", fail_output)

    row = execute_experiment_case(_request(root, config_path), 1)

    assert row["status"] == "ERROR"
    assert row["success"] is False
    assert row["failure_class"] == "OUTPUT_PUBLICATION_FAILED"
    assert row["failure_stage"] == "reporting"
    assert row["computation_status_before_failure"] == "FEASIBLE"
    assert row["resolved_item_count"] == 1
    assert row["resolved_container_inventory_count"] == 1
    assert row["error_type"] == "KeyError"
    assert row["objective_value"] is None
    assert row["official_objective"] is None
    assert row["experiment_run_dir"] is not None


def test_benchmark_uses_request_only_when_failure_precedes_resolved_input(
    root: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import container_packing.benchmarks.runner as benchmark_runner

    def fail_before_input(_request):
        raise ExperimentExecutionError(
            stage="request_setup",
            metadata={
                "requested_item_count": 10,
                "requested_container_count": 3,
            },
            cause=ValueError("bad config"),
        )

    monkeypatch.setattr(benchmark_runner, "run_experiment", fail_before_input)

    row = execute_experiment_case(_request(root), 1)

    assert row["item_count"] == 1
    assert row["container_count"] == 1
    assert row["resolved_item_count"] is None
    assert row["resolved_container_inventory_count"] is None
    assert row["failure_stage"] == "request_setup"


def test_nontechnical_failure_explanation_handles_output_failure() -> None:
    explanation = explain_failure({
        "status": "ERROR",
        "failure_class": "OUTPUT_PUBLICATION_FAILED",
        "failure_stage": "reporting",
        "construction_termination_reason": "time_limit_reached",
    })

    assert explanation is not None
    assert explanation.failure_class == "OUTPUT_PUBLICATION_FAILED"
    assert "lưu" in explanation.title.lower()
    assert any("time_limit_reached" in value for value in explanation.evidence)
