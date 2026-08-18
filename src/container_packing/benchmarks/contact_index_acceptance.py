"""Fail-closed acceptance gate for the Level 4-5 contact-index A/B protocol."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
import json

import pandas as pd

from ..provenance import sha256_file
from ..reporting import write_json, write_text


CONTACT_INDEX_SOURCE_COMMIT = "11e035d82afeb92d60adbaa0d1c7b5c2d2e6ce36"
CONTACT_INDEX_ALGORITHMS = (
    "extreme_point_best_fit",
    "extreme_point_ffd",
    "maximal_space_best_fit",
)
CONTACT_INDEX_COMPARISON_GROUPS = (
    "contact_random101_i100",
    "contact_random101_i300",
    "contact_random101_i500",
    "contact_largest_volume_i500",
    "contact_heaviest_i500",
    "contact_payload_pressure_i500",
)
CONTACT_INDEX_CORPUS_IDS = {
    "level_04": "level_04_contact_support_index_ab_v2",
    "level_05": "level_05_contact_support_index_ab_v2",
}
CONTACT_INDEX_SOURCE_CHECKSUMS = {
    "level_04": {
        "manifest_sha256": "5dd4c04485a2efdc70d2ad69005905e517212de78d6291222db8f3cd8cb0fafb",
        "results_sha256": "aec82723c4b4aa7be967afbe456b81aca106a907e4a5415e6548fde340b5f947",
        "contact_index_comparison_sha256": "c8ece463b364c8de6688f2f17561b44edfbca86267dbb35b94f55b9736db6e2e",
    },
    "level_05": {
        "manifest_sha256": "b9a92ec3fead20b89cf48043986ff9c35f4c3a1032ee66fe5334cc920fc48a8d",
        "results_sha256": "7c780e5f9363adbc55dd6a0d3af5c95ea0fbec3c077764946b8573dd3001b1ba",
        "contact_index_comparison_sha256": "a53f853d5a195b513f732efa63452c0011b0b17929a987ba33c8835d14f873e8",
    },
}


def evaluate_contact_index_acceptance(
    artifacts: Mapping[str, tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]],
) -> dict[str, Any]:
    """Evaluate both immutable A/B runs without changing either source run."""
    levels: dict[str, dict[str, Any]] = {}
    global_errors: list[str] = []
    if set(artifacts) != set(CONTACT_INDEX_CORPUS_IDS):
        global_errors.append("evidence must contain exactly level_04 and level_05")
    for level in CONTACT_INDEX_CORPUS_IDS:
        artifact = artifacts.get(level)
        if artifact is None:
            levels[level] = _empty_level_report("missing source artifact")
            continue
        levels[level] = _evaluate_level(level, *artifact)
    promoted = not global_errors and all(
        report["gate_passed"] for report in levels.values()
    )
    return {
        "schema_version": "1.0",
        "gate_id": "level_04_05_contact_support_index_v2",
        "status": "PROMOTED" if promoted else "NOT_PROMOTED",
        "contact_support_index_default_enabled": promoted,
        "source_commit": CONTACT_INDEX_SOURCE_COMMIT,
        "levels": levels,
        "errors": global_errors,
        "decision": (
            "enable_by_default_for_level_04_and_level_05"
            if promoted
            else "keep_disabled_and_end_contact_index_direction"
        ),
    }


def write_contact_index_acceptance(
    level4_run_dir: Path,
    level5_run_dir: Path,
    *,
    publish_prefix: Path,
    expected_source_checksums: Mapping[str, Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    """Read, verify, and publish one versioned report outside source run dirs."""
    artifacts: dict[str, tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]] = {}
    source_evidence: dict[str, dict[str, Any]] = {}
    for level, run_dir in (
        ("level_04", level4_run_dir),
        ("level_05", level5_run_dir),
    ):
        source = run_dir.resolve()
        manifest_path = source / "manifest.json"
        results_path = source / "benchmark" / "results.csv"
        comparison_path = source / "benchmark" / "contact_index_comparison.csv"
        missing = [
            path.name for path in (manifest_path, results_path, comparison_path)
            if not path.is_file()
        ]
        if missing:
            raise ValueError(f"{level} source artifact is incomplete: {', '.join(missing)}")
        checksums = {
            "manifest_sha256": sha256_file(manifest_path),
            "results_sha256": sha256_file(results_path),
            "contact_index_comparison_sha256": sha256_file(comparison_path),
        }
        locked = CONTACT_INDEX_SOURCE_CHECKSUMS if expected_source_checksums is None else expected_source_checksums
        expected = dict(locked.get(level, {}))
        for name, expected_value in expected.items():
            if checksums.get(name) != expected_value:
                raise ValueError(f"{level} checksum mismatch for {name}")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifacts[level] = (
            manifest,
            pd.read_csv(results_path),
            pd.read_csv(comparison_path),
        )
        source_evidence[level] = {
            "run_id": manifest.get("run_id"),
            "corpus_id": manifest.get("corpus_id"),
            "git_commit": manifest.get("git_commit"),
            "git_dirty": bool(manifest.get("git_dirty", False)),
            **checksums,
        }
    report = evaluate_contact_index_acceptance(artifacts)
    report["source_evidence"] = source_evidence
    prefix = publish_prefix.resolve()
    write_json(prefix.with_suffix(".json"), report)
    write_text(prefix.with_suffix(".md"), _markdown(report))
    return report


def _evaluate_level(
    level: str,
    manifest: dict[str, Any],
    results: pd.DataFrame,
    comparison: pd.DataFrame,
) -> dict[str, Any]:
    errors: list[str] = []
    expected_algorithms = set(CONTACT_INDEX_ALGORITHMS)
    expected_groups = set(CONTACT_INDEX_COMPARISON_GROUPS)
    if manifest.get("run_type") != "benchmark_corpus":
        errors.append("run_type must be benchmark_corpus")
    if manifest.get("level") != level:
        errors.append(f"manifest level must be {level}")
    if manifest.get("corpus_id") != CONTACT_INDEX_CORPUS_IDS[level]:
        errors.append(f"unexpected corpus_id for {level}")
    if manifest.get("status") != "SUCCESS":
        errors.append("corpus run must have status SUCCESS")
    if manifest.get("git_commit") != CONTACT_INDEX_SOURCE_COMMIT:
        errors.append("source commit does not match the V2 implementation checkpoint")
    if bool(manifest.get("git_dirty", True)):
        errors.append("source run must have git_dirty=false")

    required_results = {
        "algorithm", "comparison_group", "comparison_input_fingerprint",
        "benchmark_variant_id", "repeat", "success", "validation_valid",
        "objective_value", "used_container_count", "total_container_cost",
        "placement_signature", "selected_item_ids_checksum", "error",
    }
    missing_results = required_results - set(results.columns)
    if missing_results:
        errors.append("results missing columns: " + ", ".join(sorted(missing_results)))
        return _level_result(errors, results, comparison)
    if len(results) != 108:
        errors.append(f"expected 108 executions, found {len(results)}")
    if set(results["algorithm"].astype(str)) != expected_algorithms:
        errors.append("results do not contain exactly the three constructors")
    if set(results["comparison_group"].astype(str)) != expected_groups:
        errors.append("results do not contain exactly the six paired inputs")
    if set(results["benchmark_variant_id"].astype(str)) != {
        "contact_index_disabled", "contact_index_enabled",
    }:
        errors.append("results do not contain exactly the disabled/enabled variants")

    successful = results["success"].fillna(False).astype(bool)
    valid = results["validation_valid"].fillna(False).astype(bool)
    valid_success = successful & valid
    if not bool(valid_success.all()):
        errors.append("all 108 executions must be successful and independently VALID")
    failed = ~successful
    if bool(failed.any()) and bool(results.loc[failed, [
        "objective_value", "used_container_count", "total_container_cost",
    ]].notna().any(axis=None)):
        errors.append("failed executions must not carry an official objective")

    deterministic_count = 0
    grouped = results.groupby(
        ["comparison_group", "algorithm", "benchmark_variant_id"], sort=True,
    )
    for key, group in grouped:
        deterministic = (
            len(group) == 3
            and group["repeat"].nunique() == 3
            and bool((
                group["success"].fillna(False).astype(bool)
                & group["validation_valid"].fillna(False).astype(bool)
            ).all())
            and group["used_container_count"].nunique(dropna=False) == 1
            and group["total_container_cost"].nunique(dropna=False) == 1
            and group["placement_signature"].nunique(dropna=False) == 1
        )
        if deterministic:
            deterministic_count += 1
        else:
            errors.append(f"non-deterministic or incomplete execution group: {key}")
    if len(grouped) != 36:
        errors.append(f"expected 36 execution groups, found {len(grouped)}")

    for group_id, group in results.groupby("comparison_group", sort=True):
        if group["comparison_input_fingerprint"].nunique(dropna=False) != 1:
            errors.append(f"comparison fingerprint mismatch: {group_id}")
        if group["selected_item_ids_checksum"].nunique(dropna=False) != 1:
            errors.append(f"selected items mismatch: {group_id}")

    required_comparison = {
        "algorithm", "comparison_group", "paired_execution_count",
        "correctness_gate_passed", "construction_improvement_ratio",
        "construction_case_regression_ratio", "wall_speedup_ratio",
        "memory_overhead_ratio",
    }
    missing_comparison = required_comparison - set(comparison.columns)
    if missing_comparison:
        errors.append(
            "contact comparison missing columns: "
            + ", ".join(sorted(missing_comparison))
        )
    else:
        if len(comparison) != 18:
            errors.append(f"expected 18 paired comparisons, found {len(comparison)}")
        if set(comparison["algorithm"].astype(str)) != expected_algorithms:
            errors.append("comparison does not contain exactly the three constructors")
        if set(comparison["comparison_group"].astype(str)) != expected_groups:
            errors.append("comparison does not contain exactly the six paired inputs")
        if not comparison["paired_execution_count"].eq(3).all():
            errors.append("every comparison must contain three paired executions")
        if not comparison["correctness_gate_passed"].fillna(False).astype(bool).all():
            errors.append("enabled/disabled correctness equivalence failed")

        improvement = pd.to_numeric(
            comparison["construction_improvement_ratio"], errors="coerce",
        )
        wall_speedup = pd.to_numeric(comparison["wall_speedup_ratio"], errors="coerce")
        regression = pd.to_numeric(
            comparison["construction_case_regression_ratio"], errors="coerce",
        )
        memory = pd.to_numeric(comparison["memory_overhead_ratio"], errors="coerce")
        if any(values.isna().any() for values in (improvement, wall_speedup, regression, memory)):
            errors.append("performance or memory telemetry is incomplete")
        else:
            if float(improvement.median()) < 0.20:
                errors.append("median construction improvement is below 20%")
            if float(wall_speedup.median()) < 1.0:
                errors.append("median wall runtime regressed")
            if bool(regression.gt(0.05).any()):
                errors.append("at least one constructor/case regressed construction by more than 5%")
            if bool(memory.gt(0.20).any()):
                errors.append("peak memory overhead exceeds 20%")

    return _level_result(
        errors, results, comparison,
        deterministic_group_count=deterministic_count,
    )


def _level_result(
    errors: list[str],
    results: pd.DataFrame,
    comparison: pd.DataFrame,
    *,
    deterministic_group_count: int = 0,
) -> dict[str, Any]:
    successful = (
        results["success"].fillna(False).astype(bool)
        if "success" in results else pd.Series(dtype=bool)
    )
    valid = (
        results["validation_valid"].fillna(False).astype(bool)
        if "validation_valid" in results else pd.Series(dtype=bool)
    )
    failures: list[dict[str, Any]] = []
    if len(successful):
        for row in results.loc[~successful].itertuples(index=False):
            failures.append({
                "case_id": getattr(row, "case_id", None),
                "algorithm": getattr(row, "algorithm", None),
                "repeat": getattr(row, "repeat", None),
                "status": getattr(row, "status", None),
                "error": getattr(row, "error", None),
            })
    metrics = _performance_metrics(comparison)
    return {
        "gate_passed": not errors,
        "execution_count": int(len(results)),
        "successful_execution_count": int(successful.sum()) if len(successful) else 0,
        "valid_execution_count": int((successful & valid).sum()) if len(valid) else 0,
        "comparison_count": int(len(comparison)),
        "deterministic_group_count": int(deterministic_group_count),
        "performance": metrics,
        "failures": failures,
        "errors": errors,
    }


def _performance_metrics(comparison: pd.DataFrame) -> dict[str, Any]:
    required = {
        "construction_improvement_ratio", "construction_case_regression_ratio",
        "wall_speedup_ratio", "memory_overhead_ratio", "correctness_gate_passed",
    }
    if comparison.empty or not required.issubset(comparison.columns):
        return {}
    improvement = pd.to_numeric(comparison["construction_improvement_ratio"], errors="coerce")
    wall = pd.to_numeric(comparison["wall_speedup_ratio"], errors="coerce")
    regression = pd.to_numeric(
        comparison["construction_case_regression_ratio"], errors="coerce",
    )
    memory = pd.to_numeric(comparison["memory_overhead_ratio"], errors="coerce")
    return {
        "median_construction_improvement_ratio": _median(improvement),
        "median_wall_speedup_ratio": _median(wall),
        "construction_regression_over_5_percent_count": int(regression.gt(0.05).sum()),
        "wall_regression_count": int(wall.lt(1.0).sum()),
        "maximum_memory_overhead_ratio": (
            None if memory.dropna().empty else float(memory.max())
        ),
        "correctness_failure_count": int(
            (~comparison["correctness_gate_passed"].fillna(False).astype(bool)).sum()
        ),
    }


def _median(values: pd.Series) -> float | None:
    clean = values.dropna()
    return None if clean.empty else float(clean.median())


def _empty_level_report(error: str) -> dict[str, Any]:
    return {
        "gate_passed": False,
        "execution_count": 0,
        "successful_execution_count": 0,
        "valid_execution_count": 0,
        "comparison_count": 0,
        "deterministic_group_count": 0,
        "performance": {},
        "failures": [],
        "errors": [error],
    }


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Contact/Support Index V2 — Evidence ngày 2026-08-18",
        "",
        f"Trạng thái: **{report['status']}**.",
        "",
        "Index tiếp tục mặc định tắt. Best Fit, FFD và MES vẫn dùng đường brute-force hiện hành.",
        "",
        "| Level | VALID | Deterministic | Construction trung vị | Wall speedup | Regression >5% | Memory tối đa |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for level in ("level_04", "level_05"):
        value = report["levels"][level]
        metrics = value["performance"]
        lines.append(
            "| {level} | {valid}/{total} | {det}/36 | {construction} | {wall} | {regression} | {memory} |".format(
                level=level,
                valid=value["valid_execution_count"],
                total=value["execution_count"],
                det=value["deterministic_group_count"],
                construction=_percent(metrics.get("median_construction_improvement_ratio")),
                wall=_ratio(metrics.get("median_wall_speedup_ratio")),
                regression=metrics.get("construction_regression_over_5_percent_count", "—"),
                memory=_percent(metrics.get("maximum_memory_overhead_ratio")),
            )
        )
    lines.extend([
        "",
        "## Lý do không promote",
        "",
    ])
    for level in ("level_04", "level_05"):
        for error in report["levels"][level]["errors"]:
            lines.append(f"- `{level}`: {error}.")
    failures = [
        (level, failure)
        for level in ("level_04", "level_05")
        for failure in report["levels"][level]["failures"]
    ]
    if failures:
        lines.extend(["", "## Lỗi kỹ thuật quan sát được", ""])
        for level, failure in failures:
            lines.append(
                f"- `{level}` / `{failure.get('case_id')}` / `{failure.get('algorithm')}` / "
                f"repeat {failure.get('repeat')}: `{failure.get('error')}`."
            )
        lines.append("- Các row lỗi không có official objective và không được dùng cho kết luận chất lượng.")
    lines.extend([
        "",
        "## Quyết định",
        "",
        "Không bật index mặc định, không merge implementation V2 vào `develop` và không phát triển V3.",
        "Artifact này là research evidence, không tham gia ranking canonical.",
        "",
        "## Provenance",
        "",
        f"- Commit nguồn: `{report['source_commit']}`; cả hai manifest ghi `git_dirty=false`.",
    ])
    for level in ("level_04", "level_05"):
        evidence = report.get("source_evidence", {}).get(level, {})
        lines.append(f"- `{level}` run: `{evidence.get('run_id')}`.")
        lines.append(f"  - manifest SHA-256: `{evidence.get('manifest_sha256')}`")
        lines.append(f"  - results SHA-256: `{evidence.get('results_sha256')}`")
        lines.append(
            "  - contact comparison SHA-256: "
            f"`{evidence.get('contact_index_comparison_sha256')}`"
        )
    return "\n".join(lines) + "\n"


def _percent(value: Any) -> str:
    return "—" if value is None else f"{float(value) * 100:.2f}%"


def _ratio(value: Any) -> str:
    return "—" if value is None else f"{float(value):.3f}×"
