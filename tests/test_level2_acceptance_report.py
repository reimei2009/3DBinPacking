from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from container_packing.benchmarks.level2_acceptance import (
    build_level2_acceptance_report,
    inspect_benchmark_run,
    write_level2_acceptance_report,
)


def _benchmark_run(
    tmp_path: Path,
    name: str,
    *,
    invalid: bool = False,
    mpv: bool = False,
    reference_kind: str = "best_observed",
) -> Path:
    run = tmp_path / name
    benchmark = run / "benchmark"
    benchmark.mkdir(parents=True)
    rows = []
    scenarios = [f"mpv_case_{index:02d}" for index in range(27)] if mpv else ["case"]
    algorithms = (
        ("extreme_point_best_fit", "extreme_point_ffd")
        if mpv else ("extreme_point_best_fit",)
    )
    for scenario in scenarios:
        for algorithm in algorithms:
            for repeat in (1, 2):
                rows.append({
            "scenario_id": scenario,
            "algorithm": algorithm,
            "random_seed": 42,
            "repeat": repeat,
            "input_fingerprint": f"input-{scenario}",
            "selected_item_ids_checksum": f"items-{scenario}",
            "dataset_family": "mpv_fixed_orientation_exact_support" if mpv else "internal",
            "success": not invalid,
            "validation_valid": not invalid,
            "official_objective": None if invalid else "{'used_container_count': 2, 'total_container_cost': 2.0}",
            "objective_value": None if invalid else 2000002.0,
            "placement_signature": None if invalid else "same",
            "algorithm_runtime_seconds": 1.25,
            "peak_rss_bytes": 1000000,
            "pipeline_phase_runtime_seconds": "{'algorithm': 1.0, 'independent_validation': 0.1}",
            "inventory_search_phase_runtime_seconds": "{'construction': 1.0}",
            "incumbent_acquisition_cardinality_ladder": "[1, 2]",
            "search_termination_reason": "valid_consolidated" if not invalid else "validation_failed",
            "reference_kind": reference_kind if mpv else None,
                })
    pd.DataFrame(rows).to_csv(benchmark / "results.csv", index=False)
    if mpv:
        pd.DataFrame({
            "outcome_for_a": ["WIN", "LOSS", *(["TIE"] * 25)],
        }).to_csv(benchmark / "pairwise_outcomes.csv", index=False)
    return run


def test_level2_acceptance_report_stays_blocked_without_mpv(tmp_path) -> None:
    runs = [(name, _benchmark_run(tmp_path, name)) for name in ("fleet500", "fleet5000", "scale")]
    report = build_level2_acceptance_report(internal_runs=runs)
    assert report["status"] == "BLOCKED_EXTERNAL_CORPUS"
    assert report["internal_acceptance_passed"] is True
    assert report["promotion_inventory_orchestration_to_level_03_allowed"] is False
    json_path, md_path = write_level2_acceptance_report(report, tmp_path / "report")
    assert json.loads(json_path.read_text(encoding="utf-8"))["status"] == "BLOCKED_EXTERNAL_CORPUS"
    assert "Chưa có bundle MPV" in md_path.read_text(encoding="utf-8")


def test_level2_acceptance_report_passes_only_with_valid_mpv(tmp_path) -> None:
    runs = [(name, _benchmark_run(tmp_path, name)) for name in ("fleet500", "fleet5000", "scale")]
    mpv = _benchmark_run(tmp_path, "mpv", mpv=True)
    report = build_level2_acceptance_report(internal_runs=runs, mpv_run=mpv)
    assert report["status"] == "PASS"
    assert all(report["mpv_protocol_checks"].values())
    assert report["promotion_inventory_orchestration_to_level_03_allowed"] is True


def test_level2_acceptance_reads_legacy_reference_but_does_not_accept_it(tmp_path) -> None:
    runs = [(name, _benchmark_run(tmp_path, name)) for name in ("fleet500", "fleet5000", "scale")]
    mpv = _benchmark_run(tmp_path, "mpv-legacy", mpv=True, reference_kind="best_known")
    evidence = inspect_benchmark_run("mpv", mpv)
    assert evidence.reference_kinds == ("best_known",)
    assert evidence.legacy_reference_kind_detected is True
    report = build_level2_acceptance_report(internal_runs=runs, mpv_run=mpv)
    assert report["status"] == "FAIL_MPV_ACCEPTANCE"
    assert report["mpv_protocol_checks"]["canonical_best_observed_reference"] is False


def test_acceptance_evidence_rejects_failed_row_with_objective(tmp_path) -> None:
    run = _benchmark_run(tmp_path, "invalid", invalid=True)
    path = run / "benchmark" / "results.csv"
    frame = pd.read_csv(path)
    frame.loc[0, "objective_value"] = 123.0
    frame.to_csv(path, index=False)
    evidence = inspect_benchmark_run("invalid", run)
    assert evidence.objective_invariant_valid is False
