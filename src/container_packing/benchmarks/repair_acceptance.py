"""Acceptance gate for the bounded Level 3 repair A/B protocol."""

from __future__ import annotations

from pathlib import Path
from typing import Any
import json

import pandas as pd

from ..reporting import write_json, write_text


LEVEL3_REPAIR_CORPUS_ID = "level_03_repair_ab_100_500_v1"
LEVEL3_REPAIR_ALGORITHMS = (
    "extreme_point_best_fit",
    "extreme_point_ffd",
    "maximal_space_best_fit",
)
LEVEL3_REPAIR_COMPARISON_GROUPS = (
    "repair_prefix_i100", "repair_random101_i100",
    "repair_prefix_i300", "repair_random101_i300",
    "repair_prefix_i500", "repair_random101_i500",
)


def evaluate_level3_repair_acceptance(
    manifest: dict[str, Any],
    results: pd.DataFrame,
    comparison: pd.DataFrame,
) -> dict[str, Any]:
    """Evaluate a complete immutable A/B artifact without changing its source."""
    errors: list[str] = []
    expected_algorithms = set(LEVEL3_REPAIR_ALGORITHMS)
    expected_groups = set(LEVEL3_REPAIR_COMPARISON_GROUPS)
    if manifest.get("run_type") != "benchmark_corpus":
        errors.append("run_type must be benchmark_corpus")
    if manifest.get("level") != "level_03":
        errors.append("manifest level must be level_03")
    if manifest.get("corpus_id") != LEVEL3_REPAIR_CORPUS_ID:
        errors.append(f"corpus_id must be {LEVEL3_REPAIR_CORPUS_ID}")
    if manifest.get("status") != "SUCCESS":
        errors.append("corpus run must have status SUCCESS")

    required_results = {
        "algorithm", "comparison_group", "comparison_input_fingerprint",
        "benchmark_variant_id", "repeat", "success", "validation_valid",
        "used_container_count", "total_container_cost", "objective_value",
        "placement_signature", "selected_item_ids_checksum",
        "container_consolidation_runtime_seconds",
        "container_consolidation_termination_reason",
    }
    missing = required_results - set(results.columns)
    if missing:
        errors.append("results missing columns: " + ", ".join(sorted(missing)))
        return _result(errors, results, comparison)
    if len(results) != 72:
        errors.append(f"expected 72 executions, found {len(results)}")
    if set(results["algorithm"].astype(str)) != expected_algorithms:
        errors.append("results do not contain exactly the three qualified constructors")
    if set(results["comparison_group"].astype(str)) != expected_groups:
        errors.append("results do not contain exactly the six paired inputs")
    variants = set(results["benchmark_variant_id"].astype(str))
    if variants != {"repair_disabled", "repair_enabled"}:
        errors.append("results must contain repair_disabled and repair_enabled")

    successful = results["success"].fillna(False).astype(bool)
    valid = results["validation_valid"].fillna(False).astype(bool)
    if not bool((successful & valid).all()):
        errors.append("all 72 executions must be successful and independently VALID")
    failed = ~successful
    if bool(failed.any()):
        failed_objective = results.loc[failed, [
            "objective_value", "used_container_count", "total_container_cost",
        ]].notna().any(axis=1)
        if bool(failed_objective.any()):
            errors.append("failed executions must not carry an official objective")
    if bool(results.loc[successful, [
        "used_container_count", "total_container_cost", "objective_value",
    ]].isna().any(axis=None)):
        errors.append("successful executions must carry the complete official objective")

    deterministic_groups = 0
    grouped = results.groupby(
        ["comparison_group", "algorithm", "benchmark_variant_id"], sort=True,
    )
    for key, group in grouped:
        deterministic = (
            len(group) == 2
            and group["repeat"].nunique() == 2
            and group["used_container_count"].nunique(dropna=False) == 1
            and group["total_container_cost"].nunique(dropna=False) == 1
            and group["placement_signature"].nunique(dropna=False) == 1
        )
        if deterministic:
            deterministic_groups += 1
        else:
            errors.append(f"non-deterministic repair group: {key}")
    if len(grouped) != 36:
        errors.append(f"expected 36 variant groups, found {len(grouped)}")

    for group_id, group in results.groupby("comparison_group", sort=True):
        if group["comparison_input_fingerprint"].nunique(dropna=False) != 1:
            errors.append(f"comparison fingerprint mismatch: {group_id}")
        if group["selected_item_ids_checksum"].nunique(dropna=False) != 1:
            errors.append(f"selected items mismatch: {group_id}")

    required_comparison = {
        "algorithm", "comparison_group", "outcome", "incumbent_preserved",
        "runtime_without_repair_p50_seconds", "runtime_with_repair_p50_seconds",
        "repair_runtime_p50_seconds", "repair_termination_reason",
    }
    missing_comparison = required_comparison - set(comparison.columns)
    if missing_comparison:
        errors.append(
            "repair comparison missing columns: "
            + ", ".join(sorted(missing_comparison))
        )
    else:
        if len(comparison) != 18:
            errors.append(f"expected 18 algorithm-paired comparisons, found {len(comparison)}")
        if set(comparison["algorithm"].astype(str)) != expected_algorithms:
            errors.append("repair comparison mixes or omits constructors")
        observed_pairs = {
            (str(row.comparison_group), str(row.algorithm))
            for row in comparison.itertuples(index=False)
        }
        expected_pairs = {
            (group, algorithm)
            for group in expected_groups
            for algorithm in expected_algorithms
        }
        if observed_pairs != expected_pairs or len(observed_pairs) != len(comparison):
            errors.append("repair comparison must contain each input/constructor pair exactly once")
        outcomes = comparison["outcome"].astype(str)
        if outcomes.eq("REGRESSION").any() or outcomes.eq("NO_VALID_REPAIR_RESULT").any():
            errors.append("repair must not regress or lose a valid incumbent")
        if not outcomes.eq("IMPROVED").any():
            errors.append("repair must produce at least one objective improvement")
        if not comparison["incumbent_preserved"].fillna(False).astype(bool).all():
            errors.append("every pair must preserve the validated incumbent")
        runtime_columns = [
            "runtime_without_repair_p50_seconds",
            "runtime_with_repair_p50_seconds",
            "repair_runtime_p50_seconds",
        ]
        if comparison[runtime_columns].isna().any(axis=None):
            errors.append("repair/runtime-overhead telemetry is incomplete")
        reasons = comparison["repair_termination_reason"].fillna("").astype(str).str.strip()
        if reasons.eq("").any():
            errors.append("repair termination reason is incomplete")

    enabled = results["benchmark_variant_id"].astype(str).eq("repair_enabled")
    enabled_runtime = pd.to_numeric(
        results.loc[enabled, "container_consolidation_runtime_seconds"], errors="coerce",
    )
    enabled_reasons = (
        results.loc[enabled, "container_consolidation_termination_reason"]
        .fillna("").astype(str).str.strip()
    )
    if enabled_runtime.isna().any() or enabled_reasons.eq("").any():
        errors.append("repair-enabled execution telemetry is incomplete")

    return _result(
        errors, results, comparison,
        deterministic_group_count=deterministic_groups,
    )


def write_level3_repair_acceptance(run_dir: Path) -> dict[str, Any]:
    """Evaluate one run and write diagnostic evidence inside that run only."""
    source = run_dir.resolve()
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    results = pd.read_csv(source / "benchmark" / "results.csv")
    comparison = pd.read_csv(source / "benchmark" / "repair_comparison.csv")
    report = evaluate_level3_repair_acceptance(manifest, results, comparison)
    write_json(source / "benchmark" / "level3_repair_acceptance_gate.json", report)
    write_text(source / "reports" / "level3_repair_acceptance.md", _markdown(report))
    return report


def _result(
    errors: list[str], results: pd.DataFrame, comparison: pd.DataFrame,
    *, deterministic_group_count: int = 0,
) -> dict[str, Any]:
    outcome_counts = (
        comparison["outcome"].astype(str).value_counts().sort_index().to_dict()
        if "outcome" in comparison else {}
    )
    return {
        "schema_version": "1.0",
        "gate_id": "level_03_repair_ui_acceptance_v1",
        "status": "PASS" if not errors else "NOT_PROMOTED",
        "repair_ui_qualified": not errors,
        "execution_count": int(len(results)),
        "comparison_count": int(len(comparison)),
        "deterministic_group_count": int(deterministic_group_count),
        "outcome_counts": {str(key): int(value) for key, value in outcome_counts.items()},
        "errors": errors,
    }


def _markdown(report: dict[str, Any]) -> str:
    errors = report["errors"]
    error_lines = "\n".join(f"- {value}" for value in errors) or "- Không có."
    return (
        "# Nghiệm thu repair UI Level 3\n\n"
        f"- Trạng thái: **{report['status']}**.\n"
        f"- Lượt chạy: {report['execution_count']}/72.\n"
        f"- So sánh ghép cặp: {report['comparison_count']}/18.\n"
        f"- Nhóm deterministic: {report['deterministic_group_count']}/36.\n"
        f"- Kết quả A/B: `{report['outcome_counts']}`.\n\n"
        "## Lỗi gate\n\n"
        f"{error_lines}\n"
    )
