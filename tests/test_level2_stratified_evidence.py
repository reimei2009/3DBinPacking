import json
from pathlib import Path

import pandas as pd
import pytest

from container_packing.benchmarks.stratified_evidence import (
    build_stratified_evidence,
    verify_stratified_evidence_checksums,
)
from container_packing.benchmarks.distribution import (
    build_determinism_evidence,
    build_pairwise_outcomes,
)


def _write_run(
    root: Path, stratum: str, corpus_id: str, case_count: int, execution_count: int,
) -> Path:
    run_dir = root / stratum
    benchmark = run_dir / "benchmark"
    benchmark.mkdir(parents=True)
    repeats = 3
    algorithms = (
        "extreme_point_best_fit", "extreme_point_ffd", "maximal_space_best_fit",
    )
    rows = []
    for case_index in range(case_count):
        for algorithm in algorithms:
            for repeat in range(1, repeats + 1):
                rows.append({
                    "level": "level_02", "case_id": f"{stratum}-{case_index}",
                    "scenario_id": f"{stratum}-{case_index}",
                    "input_fingerprint": f"fingerprint-{case_index}",
                    "selected_item_ids_checksum": f"items-{case_index}",
                    "algorithm": algorithm, "random_seed": 42, "repeat": repeat,
                    "success": True, "validation_valid": True, "status": "FEASIBLE",
                    "objective_value": 1.0, "used_container_count": 2,
                    "total_container_cost": 2000.0,
                    "placement_signature": f"{case_index}-{algorithm}",
                    "item_count": 20, "wall_runtime_seconds": 1.0,
                    "peak_rss_bytes": 100, "dataset_family": "generated",
                    "scale_bucket": "small", "benchmark_stratum": stratum,
                })
    assert len(rows) == execution_count
    results = pd.DataFrame(rows)
    results.to_csv(benchmark / "results.csv", index=False)
    build_determinism_evidence(results).to_csv(
        benchmark / "determinism_evidence.csv", index=False,
    )
    build_pairwise_outcomes(results).to_csv(
        benchmark / "pairwise_outcomes.csv", index=False,
    )
    (run_dir / "manifest.json").write_text(json.dumps({
        "corpus_id": corpus_id, "case_count": case_count,
        "execution_count": execution_count, "git_commit": "a" * 40,
        "git_dirty": False,
    }), encoding="utf-8")
    return run_dir


def test_stratified_evidence_requires_all_three_valid_deterministic_layers(
    tmp_path: Path,
) -> None:
    runs = {
        "random_distribution": _write_run(
            tmp_path, "random_distribution",
            "level_02_generated_1k_500_random_v2_candidate", 60, 540,
        ),
        "stress": _write_run(
            tmp_path, "stress", "level_02_generated_1k_500_stress_v2_candidate",
            18, 162,
        ),
        "prefix_regression": _write_run(
            tmp_path, "prefix_regression",
            "level_02_generated_1k_500_prefix_regression_v2", 6, 54,
        ),
    }

    report = build_stratified_evidence(runs)

    assert report["status"] == "PASS"
    assert report["functional_gate"]["status"] == "PASS"
    assert report["provenance_gate"]["status"] == "PASS"
    assert report["governance_decision"] == "CANONICAL_PROMOTION_ALLOWED"
    assert report["promotion_to_canonical_allowed"] is True
    assert report["case_count"] == 84
    assert report["execution_count"] == 756
    assert all(value["passed"] for value in report["strata"])
    assert all(value["ties"] == 60 for value in report["random_distribution_pairwise_vs_best_fit"])
    assert verify_stratified_evidence_checksums(report, runs) == ()


def test_stratified_evidence_blocks_dirty_source_from_canonical_promotion(
    tmp_path: Path,
) -> None:
    runs = {
        "random_distribution": _write_run(
            tmp_path, "random_distribution",
            "level_02_generated_1k_500_random_v2_candidate", 60, 540,
        ),
        "stress": _write_run(
            tmp_path, "stress", "level_02_generated_1k_500_stress_v2_candidate",
            18, 162,
        ),
        "prefix_regression": _write_run(
            tmp_path, "prefix_regression",
            "level_02_generated_1k_500_prefix_regression_v2", 6, 54,
        ),
    }
    manifest_path = runs["stress"] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["git_dirty"] = True
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    report = build_stratified_evidence(runs)

    assert report["functional_gate"]["status"] == "PASS"
    assert report["provenance_gate"]["status"] == "FAIL"
    assert report["governance_decision"] == "CANONICAL_PENDING_CLEAN_RERUN"
    assert report["promotion_to_canonical_allowed"] is False


def test_stratified_evidence_fails_closed_for_missing_artifact(tmp_path: Path) -> None:
    run = _write_run(
        tmp_path, "random_distribution",
        "level_02_generated_1k_500_random_v2_candidate", 60, 540,
    )
    (run / "benchmark/pairwise_outcomes.csv").unlink()

    with pytest.raises(ValueError, match="thiếu artifact bắt buộc"):
        build_stratified_evidence({
            "random_distribution": run,
            "stress": run,
            "prefix_regression": run,
        })


def test_published_stratified_evidence_detects_checksum_mismatch(tmp_path: Path) -> None:
    runs = {
        "random_distribution": _write_run(
            tmp_path, "random_distribution",
            "level_02_generated_1k_500_random_v2_candidate", 60, 540,
        ),
        "stress": _write_run(
            tmp_path, "stress", "level_02_generated_1k_500_stress_v2_candidate",
            18, 162,
        ),
        "prefix_regression": _write_run(
            tmp_path, "prefix_regression",
            "level_02_generated_1k_500_prefix_regression_v2", 6, 54,
        ),
    }
    report = build_stratified_evidence(runs)
    with (runs["random_distribution"] / "benchmark/results.csv").open(
        "a", encoding="utf-8",
    ) as stream:
        stream.write("\n")

    errors = verify_stratified_evidence_checksums(report, runs)

    assert errors == ("random_distribution/results: checksum mismatch",)
