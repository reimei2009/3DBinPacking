from __future__ import annotations

import json

import pandas as pd

from container_packing.benchmarks.repair_acceptance import (
    LEVEL3_REPAIR_ALGORITHMS,
    LEVEL3_REPAIR_COMPARISON_GROUPS,
    evaluate_level3_repair_acceptance,
    write_level3_repair_acceptance,
)


def _artifact() -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    results = []
    comparisons = []
    for group in LEVEL3_REPAIR_COMPARISON_GROUPS:
        item_count = int(group.rsplit("i", 1)[1])
        for algorithm in LEVEL3_REPAIR_ALGORITHMS:
            improved = group == LEVEL3_REPAIR_COMPARISON_GROUPS[0] and algorithm == LEVEL3_REPAIR_ALGORITHMS[0]
            before = 4
            after = 3 if improved else before
            for variant, containers in (
                ("repair_disabled", before), ("repair_enabled", after),
            ):
                for repeat in (1, 2):
                    results.append({
                        "algorithm": algorithm,
                        "comparison_group": group,
                        "comparison_input_fingerprint": f"physical-{group}",
                        "benchmark_variant_id": variant,
                        "repeat": repeat,
                        "success": True,
                        "validation_valid": True,
                        "used_container_count": containers,
                        "total_container_cost": containers * 2000,
                        "objective_value": float(containers),
                        "placement_signature": f"{group}-{algorithm}-{variant}",
                        "selected_item_ids_checksum": f"items-{group}",
                        "container_consolidation_runtime_seconds": (
                            0.0 if variant == "repair_disabled" else 2.0
                        ),
                        "container_consolidation_termination_reason": (
                            "disabled" if variant == "repair_disabled" else
                            "valid_consolidated" if improved else
                            "heuristic_consolidation_failed"
                        ),
                    })
            comparisons.append({
                "algorithm": algorithm,
                "comparison_group": group,
                "outcome": "IMPROVED" if improved else "UNCHANGED",
                "incumbent_preserved": True,
                "runtime_without_repair_p50_seconds": 4.0,
                "runtime_with_repair_p50_seconds": 6.0,
                "repair_runtime_p50_seconds": 2.0,
                "repair_termination_reason": (
                    "valid_consolidated" if improved else "heuristic_consolidation_failed"
                ),
                "item_count": item_count,
            })
    manifest = {
        "run_type": "benchmark_corpus",
        "level": "level_03",
        "corpus_id": "level_03_repair_ab_100_500_v1",
        "status": "SUCCESS",
    }
    return manifest, pd.DataFrame(results), pd.DataFrame(comparisons)


def test_level3_repair_acceptance_passes_complete_valid_ab() -> None:
    report = evaluate_level3_repair_acceptance(*_artifact())
    assert report["status"] == "PASS"
    assert report["repair_ui_qualified"] is True
    assert report["execution_count"] == 72
    assert report["comparison_count"] == 18
    assert report["deterministic_group_count"] == 36
    assert report["outcome_counts"] == {"IMPROVED": 1, "UNCHANGED": 17}


def test_level3_repair_acceptance_rejects_regression_and_nondeterminism() -> None:
    manifest, results, comparison = _artifact()
    comparison.loc[0, "outcome"] = "REGRESSION"
    comparison.loc[0, "incumbent_preserved"] = False
    results.loc[1, "placement_signature"] = "changed"
    report = evaluate_level3_repair_acceptance(manifest, results, comparison)
    assert report["status"] == "NOT_PROMOTED"
    assert report["repair_ui_qualified"] is False
    assert any("non-deterministic" in value for value in report["errors"])
    assert any("regress" in value for value in report["errors"])


def test_level3_repair_acceptance_writer_keeps_evidence_in_run_dir(tmp_path) -> None:
    manifest, results, comparison = _artifact()
    benchmark_dir = tmp_path / "benchmark"
    benchmark_dir.mkdir()
    (tmp_path / "reports").mkdir()
    (tmp_path / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8",
    )
    results.to_csv(benchmark_dir / "results.csv", index=False)
    comparison.to_csv(benchmark_dir / "repair_comparison.csv", index=False)

    report = write_level3_repair_acceptance(tmp_path)

    assert report["status"] == "PASS"
    assert (benchmark_dir / "level3_repair_acceptance_gate.json").is_file()
    markdown = (tmp_path / "reports" / "level3_repair_acceptance.md").read_text(
        encoding="utf-8",
    )
    assert "Nghiệm thu repair UI Level 3" in markdown
