from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from container_packing.benchmarks.mes_deadline_reliability import (
    evaluate_mes_deadline_reliability,
)
from container_packing.provenance import sha256_file
from scripts.build_mes_deadline_reliability_report import _markdown


@pytest.mark.parametrize("level", ["level_04", "level_05"])
def test_mes_deadline_diagnostic_corpus_has_three_cases_and_nine_executions(level: str) -> None:
    payload = yaml.safe_load(Path(
        f"config/{level}/benchmarks/mes_deadline_reliability_manual.yaml"
    ).read_text(encoding="utf-8"))
    matrix = payload["matrix"]
    case_count = len(matrix["scales"]) * sum(
        len(selection.get("selection_seeds", [None]))
        for selection in matrix["selections"]
    )
    assert case_count == 3
    assert payload["repeats"] == 3
    assert case_count * len(matrix["algorithms"]) * payload["repeats"] == 9
    assert {scale["item_count"] for scale in matrix["scales"]} == {500}
    assert matrix["algorithms"] == ["maximal_space_best_fit"]


def _diagnostic_run(
    root: Path, level: str, *, eligible: bool = True,
    operation_seconds: float = 0.2, overshoot: float = 0.0,
) -> Path:
    run = root / level
    benchmark = run / "benchmark"
    benchmark.mkdir(parents=True, exist_ok=True)
    (run / "manifest.json").write_text(json.dumps({
        "run_type": "benchmark_corpus",
        "run_id": f"diagnostic-{level}",
        "corpus_id": f"{level}_mes_deadline_reliability_v1",
        "status": "SUCCESS",
        "execution_count": 1,
        "successful_execution_count": 1,
        "git_commit": "source-commit",
        "git_dirty": False,
    }), encoding="utf-8")
    pd.DataFrame([{
        "case_id": "diagnostic_case",
        "algorithm": "maximal_space_best_fit",
        "random_seed": 42,
        "repeat": 1,
        "status": "FEASIBLE",
        "success": True,
        "validation_valid": True,
        "official_objective": "{'used_container_count': 1, 'total_container_cost': 1.0}",
        "placement_signature": "stable-signature",
        "deadline_reliability_enabled": True,
        "deadline_reliability_classification": "NORMAL" if eligible else "SYSTEM_SUSPEND_DETECTED",
        "deadline_reliability_evidence_eligible": eligible,
        "deadline_reliability_deadline_overshoot_seconds": overshoot,
        "deadline_reliability_max_operation": "load_transfer",
        "deadline_reliability_max_operation_active_seconds": operation_seconds,
    }]).to_csv(benchmark / "results.csv", index=False)
    return run


def test_diagnostic_evaluator_is_fail_closed_and_targets_long_operation(tmp_path: Path) -> None:
    level4 = _diagnostic_run(tmp_path, "level_04")
    level5 = _diagnostic_run(tmp_path, "level_05")
    decision = evaluate_mes_deadline_reliability(
        {"level_04": level4, "level_05": level5},
        expected_executions_per_level=1,
        expected_repeats_per_group=1,
    )
    assert decision.decision == "NO_COOPERATIVE_HARDENING_REQUIRED"

    _diagnostic_run(tmp_path, "level_05", operation_seconds=1.5)
    decision = evaluate_mes_deadline_reliability(
        {"level_04": level4, "level_05": level5},
        expected_executions_per_level=1,
        expected_repeats_per_group=1,
    )
    assert decision.decision == "TARGETED_HARDENING_REQUIRED"
    assert decision.operation_to_harden == "load_transfer"

    _diagnostic_run(tmp_path, "level_05", eligible=False)
    decision = evaluate_mes_deadline_reliability(
        {"level_04": level4, "level_05": level5},
        expected_executions_per_level=1,
        expected_repeats_per_group=1,
    )
    assert decision.decision == "NO_COOPERATIVE_HARDENING_REQUIRED_ENVIRONMENTAL_NOISE"
    assert decision.evidence_eligible is False


def test_diagnostic_evaluator_rejects_incomplete_artifacts(tmp_path: Path) -> None:
    level4 = _diagnostic_run(tmp_path, "level_04")
    level5 = tmp_path / "level_05"
    level5.mkdir()
    with pytest.raises(ValueError, match="Incomplete diagnostic artifacts"):
        evaluate_mes_deadline_reliability(
            {"level_04": level4, "level_05": level5},
            expected_executions_per_level=1,
            expected_repeats_per_group=1,
        )


def test_diagnostic_evaluator_rejects_provenance_and_checksum_mismatch(
    tmp_path: Path,
) -> None:
    level4 = _diagnostic_run(tmp_path, "level_04")
    level5 = _diagnostic_run(tmp_path, "level_05")
    with pytest.raises(ValueError, match="Unexpected source commit"):
        evaluate_mes_deadline_reliability(
            {"level_04": level4, "level_05": level5},
            expected_executions_per_level=1,
            expected_repeats_per_group=1,
            expected_source_commit="different-commit",
        )

    locks = {
        level: {
            "manifest_sha256": sha256_file(run / "manifest.json"),
            "results_sha256": sha256_file(run / "benchmark" / "results.csv"),
        }
        for level, run in {"level_04": level4, "level_05": level5}.items()
    }
    locks["level_05"]["results_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="Results checksum mismatch"):
        evaluate_mes_deadline_reliability(
            {"level_04": level4, "level_05": level5},
            expected_executions_per_level=1,
            expected_repeats_per_group=1,
            expected_checksums=locks,
        )


def test_report_builder_explains_decision_without_reinterpreting_portfolio(
    tmp_path: Path,
) -> None:
    level4 = _diagnostic_run(tmp_path, "level_04")
    level5 = _diagnostic_run(tmp_path, "level_05")
    decision = evaluate_mes_deadline_reliability(
        {"level_04": level4, "level_05": level5},
        expected_executions_per_level=1,
        expected_repeats_per_group=1,
        expected_source_commit="source-commit",
    )
    report = _markdown(decision.payload(), "test_report")
    assert "NO_COOPERATIVE_HARDENING_REQUIRED" in report
    assert "Constructor Portfolio V1 vẫn" in report
    assert "`NOT_PROMOTED`" in report
