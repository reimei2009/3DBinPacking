from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from container_packing.benchmarks.canonical_evidence import (
    CANONICAL_CORPUS_ID,
    build_canonical_benchmark_evidence,
    write_canonical_benchmark_evidence,
)


def _canonical_run(tmp_path: Path, *, invalidate_one: bool = False) -> Path:
    run = tmp_path / "canonical"
    benchmark = run / "benchmark"
    benchmark.mkdir(parents=True)
    algorithms = (
        "extreme_point_best_fit", "extreme_point_ffd", "maximal_space_best_fit",
    )
    rows = []
    for case_index in range(24):
        for algorithm in algorithms:
            count = 5
            if case_index == 0 and algorithm == "maximal_space_best_fit":
                count = 4
            if case_index == 1 and algorithm == "maximal_space_best_fit":
                count = 6
            for repeat in (1, 2):
                valid = not (invalidate_one and case_index == 0 and repeat == 1 and algorithm == algorithms[0])
                rows.append({
                    "level": "level_02",
                    "case_id": f"case-{case_index:02d}",
                    "scenario_id": f"case-{case_index:02d}",
                    "algorithm": algorithm,
                    "random_seed": 42,
                    "repeat": repeat,
                    "success": valid,
                    "validation_valid": valid,
                    "status": "FEASIBLE" if valid else "INVALID_SOLUTION",
                    "official_objective": (
                        json.dumps({"used_container_count": count, "total_container_cost": count * 2000})
                        if valid else None
                    ),
                    "objective_value": count * 1_000_000 + count * 2000 if valid else None,
                    "used_container_count": count if valid else None,
                    "total_container_cost": count * 2000 if valid else None,
                    "placement_signature": f"{case_index}-{algorithm}" if valid else None,
                    "input_fingerprint": f"fingerprint-{case_index}",
                    "selected_item_ids_checksum": f"checksum-{case_index}",
                    "aggregate_lower_bound": 4,
                    "item_count": 100,
                    "item_selection_strategy": "stable_random",
                    "item_selection_seed": case_index,
                    "dataset_family": "generated",
                    "scale_bucket": "medium",
                    "wall_runtime_seconds": 2.0 + repeat / 10,
                    "algorithm_runtime_seconds": 1.0,
                    "peak_rss_bytes": 100_000_000,
                })
    pd.DataFrame(rows).to_csv(benchmark / "results.csv", index=False)
    (run / "manifest.json").write_text(json.dumps({
        "corpus_id": CANONICAL_CORPUS_ID,
        "status": "SUCCESS",
        "case_count": 24,
        "execution_count": 144,
        "successful_execution_count": 143 if invalidate_one else 144,
    }), encoding="utf-8")
    return run


def test_canonical_evidence_gate_and_report(tmp_path: Path) -> None:
    report = build_canonical_benchmark_evidence(_canonical_run(tmp_path))

    assert report["status"] == "PASS"
    assert report["coverage"] == {
        "case_count": 24, "algorithm_count": 3, "repeat_count": 2,
        "execution_count": 144, "valid_execution_count": 144,
        "deterministic_group_count": 72,
    }
    assert report["paired_outcomes_vs_baseline"]["extreme_point_ffd"] == {
        "WIN": 0, "TIE": 24, "LOSS": 0,
    }
    assert report["paired_outcomes_vs_baseline"]["maximal_space_best_fit"] == {
        "WIN": 1, "TIE": 22, "LOSS": 1,
    }
    assert len(report["different_cases"]) == 6
    json_path, markdown_path = write_canonical_benchmark_evidence(
        report, tmp_path / "evidence",
    )
    assert json.loads(json_path.read_text(encoding="utf-8"))["status"] == "PASS"
    markdown = markdown_path.read_text(encoding="utf-8")
    assert "144/144" in markdown
    assert "1 thắng, 22 hòa và 1 thua" in markdown
    assert "không phải nghiệm tối ưu" in markdown


def test_canonical_evidence_fails_when_one_execution_is_invalid(tmp_path: Path) -> None:
    report = build_canonical_benchmark_evidence(
        _canonical_run(tmp_path, invalidate_one=True),
    )
    assert report["status"] == "FAIL"
    assert report["checks"]["all_success_and_independently_valid"] is False
    assert report["checks"]["manifest_counts_match"] is False
