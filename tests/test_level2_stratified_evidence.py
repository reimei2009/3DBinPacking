import json
from pathlib import Path

import pandas as pd

from container_packing.benchmarks.stratified_evidence import (
    build_stratified_evidence,
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
    pd.DataFrame(rows).to_csv(benchmark / "results.csv", index=False)
    (run_dir / "manifest.json").write_text(json.dumps({
        "corpus_id": corpus_id, "case_count": case_count,
        "execution_count": execution_count,
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
    assert report["promotion_to_canonical_allowed"] is True
    assert report["case_count"] == 84
    assert report["execution_count"] == 756
    assert all(value["passed"] for value in report["strata"])
    assert all(value["ties"] == 60 for value in report["random_distribution_pairwise_vs_best_fit"])
