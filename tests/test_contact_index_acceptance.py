from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from container_packing.benchmarks.contact_index_acceptance import (
    CONTACT_INDEX_ALGORITHMS,
    CONTACT_INDEX_COMPARISON_GROUPS,
    CONTACT_INDEX_CORPUS_IDS,
    CONTACT_INDEX_SOURCE_COMMIT,
    evaluate_contact_index_acceptance,
    write_contact_index_acceptance,
)
from container_packing.provenance import sha256_file


def _artifact(level: str) -> tuple[dict, pd.DataFrame, pd.DataFrame]:
    rows: list[dict] = []
    comparisons: list[dict] = []
    for group in CONTACT_INDEX_COMPARISON_GROUPS:
        for algorithm in CONTACT_INDEX_ALGORITHMS:
            for variant in ("contact_index_disabled", "contact_index_enabled"):
                for repeat in (1, 2, 3):
                    rows.append({
                        "case_id": f"{group}_{variant}",
                        "algorithm": algorithm,
                        "comparison_group": group,
                        "comparison_input_fingerprint": f"fingerprint-{group}",
                        "benchmark_variant_id": variant,
                        "repeat": repeat,
                        "status": "FEASIBLE",
                        "success": True,
                        "validation_valid": True,
                        "objective_value": 1001.0,
                        "used_container_count": 1,
                        "total_container_cost": 1000.0,
                        "placement_signature": f"signature-{group}-{algorithm}",
                        "selected_item_ids_checksum": f"items-{group}",
                        "error": None,
                    })
            comparisons.append({
                "algorithm": algorithm,
                "comparison_group": group,
                "paired_execution_count": 3,
                "correctness_gate_passed": True,
                "construction_improvement_ratio": 0.25,
                "construction_case_regression_ratio": 0.0,
                "wall_speedup_ratio": 1.10,
                "memory_overhead_ratio": 0.10,
            })
    manifest = {
        "run_type": "benchmark_corpus",
        "level": level,
        "run_id": f"run-{level}",
        "corpus_id": CONTACT_INDEX_CORPUS_IDS[level],
        "status": "SUCCESS",
        "git_commit": CONTACT_INDEX_SOURCE_COMMIT,
        "git_dirty": False,
    }
    return manifest, pd.DataFrame(rows), pd.DataFrame(comparisons)


def _all_artifacts():
    return {level: _artifact(level) for level in CONTACT_INDEX_CORPUS_IDS}


def test_acceptance_promotes_only_when_both_levels_pass() -> None:
    report = evaluate_contact_index_acceptance(_all_artifacts())

    assert report["status"] == "PROMOTED"
    assert report["contact_support_index_default_enabled"] is True
    assert all(value["gate_passed"] for value in report["levels"].values())


@pytest.mark.parametrize("failure_kind", ["performance", "correctness", "incomplete"])
def test_acceptance_fails_closed(failure_kind: str) -> None:
    artifacts = _all_artifacts()
    manifest, results, comparison = artifacts["level_05"]
    if failure_kind == "performance":
        comparison.loc[:, "construction_improvement_ratio"] = 0.19
    elif failure_kind == "correctness":
        comparison.loc[0, "correctness_gate_passed"] = False
    else:
        results.drop(index=results.index[-1], inplace=True)

    report = evaluate_contact_index_acceptance(artifacts)

    assert report["status"] == "NOT_PROMOTED"
    assert report["contact_support_index_default_enabled"] is False
    assert report["levels"]["level_05"]["gate_passed"] is False


def _write_source(run_dir: Path, artifact: tuple[dict, pd.DataFrame, pd.DataFrame]) -> None:
    manifest, results, comparison = artifact
    (run_dir / "benchmark").mkdir(parents=True)
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8",
    )
    results.to_csv(run_dir / "benchmark" / "results.csv", index=False)
    comparison.to_csv(
        run_dir / "benchmark" / "contact_index_comparison.csv", index=False,
    )


def test_writer_rejects_checksum_mismatch(tmp_path: Path) -> None:
    level4 = tmp_path / "level4"
    level5 = tmp_path / "level5"
    _write_source(level4, _artifact("level_04"))
    _write_source(level5, _artifact("level_05"))

    with pytest.raises(ValueError, match="checksum mismatch"):
        write_contact_index_acceptance(
            level4,
            level5,
            publish_prefix=tmp_path / "evidence" / "contact-index-v2",
            expected_source_checksums={
                "level_04": {"manifest_sha256": "not-the-real-checksum"},
            },
        )

    assert not (tmp_path / "evidence" / "contact-index-v2.json").exists()


def test_writer_locks_source_checksums_and_does_not_modify_sources(tmp_path: Path) -> None:
    level4 = tmp_path / "level4"
    level5 = tmp_path / "level5"
    _write_source(level4, _artifact("level_04"))
    _write_source(level5, _artifact("level_05"))
    before = sha256_file(level4 / "manifest.json")
    expected = {}
    for level, run_dir in (("level_04", level4), ("level_05", level5)):
        expected[level] = {
            "manifest_sha256": sha256_file(run_dir / "manifest.json"),
            "results_sha256": sha256_file(run_dir / "benchmark" / "results.csv"),
            "contact_index_comparison_sha256": sha256_file(
                run_dir / "benchmark" / "contact_index_comparison.csv"
            ),
        }

    report = write_contact_index_acceptance(
        level4,
        level5,
        publish_prefix=tmp_path / "evidence" / "contact-index-v2",
        expected_source_checksums=expected,
    )

    assert report["status"] == "PROMOTED"
    assert report["source_evidence"]["level_04"]["manifest_sha256"] == before
    assert sha256_file(level4 / "manifest.json") == before
    assert (tmp_path / "evidence" / "contact-index-v2.json").is_file()
    assert (tmp_path / "evidence" / "contact-index-v2.md").is_file()


def test_level_4_and_5_defaults_keep_contact_index_disabled(root: Path) -> None:
    from container_packing.data_loader import load_config

    for level in ("level_04", "level_05"):
        config = load_config(root / "config" / level / "default.yaml")
        algorithms = config["algorithms"]
        for algorithm in CONTACT_INDEX_ALGORITHMS:
            assert algorithms[algorithm]["contact_support_index"]["enabled"] is False
