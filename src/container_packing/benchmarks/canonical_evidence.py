"""Phát hành evidence dễ kiểm toán cho benchmark canonical Level 2."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from ..provenance import sha256_file
from .distribution import (
    build_case_algorithm_summary,
    build_case_differences,
    build_determinism_evidence,
    build_distribution_summary,
    build_pairwise_outcomes,
)


CANONICAL_CORPUS_ID = "level_02_generated_1k_500_canonical_v1"
CANONICAL_ALGORITHMS = (
    "extreme_point_best_fit",
    "extreme_point_ffd",
    "maximal_space_best_fit",
)
BASELINE_ALGORITHM = "extreme_point_best_fit"
EXPECTED_CASE_COUNT = 24
EXPECTED_REPEAT_COUNT = 2
EXPECTED_EXECUTION_COUNT = 144


def build_canonical_benchmark_evidence(run_dir: str | Path) -> dict[str, Any]:
    """Validate a persisted canonical run and derive its publication evidence."""
    run = Path(run_dir).resolve()
    manifest_path = run / "manifest.json"
    results_path = run / "benchmark" / "results.csv"
    if not manifest_path.is_file() or not results_path.is_file():
        raise ValueError(f"Canonical benchmark artifact is incomplete: {run}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    results = pd.read_csv(results_path, encoding="utf-8-sig")
    required = {
        "case_id", "algorithm", "random_seed", "repeat", "success",
        "validation_valid", "status", "official_objective", "objective_value",
        "used_container_count", "total_container_cost", "placement_signature",
        "input_fingerprint", "selected_item_ids_checksum", "aggregate_lower_bound",
        "item_count", "wall_runtime_seconds", "algorithm_runtime_seconds",
        "peak_rss_bytes",
    }
    missing = sorted(required - set(results.columns))
    if missing:
        raise ValueError(f"Canonical benchmark is missing columns: {', '.join(missing)}")

    success = results["success"].map(_as_bool)
    valid = results["validation_valid"].map(_as_bool)
    failure_rows = results[~success]
    failure_objective_is_null = bool(
        failure_rows.empty
        or (
            failure_rows["official_objective"].isna()
            & pd.to_numeric(failure_rows["objective_value"], errors="coerce").isna()
            & pd.to_numeric(failure_rows["used_container_count"], errors="coerce").isna()
            & pd.to_numeric(failure_rows["total_container_cost"], errors="coerce").isna()
        ).all()
    )
    fingerprints_per_case = results.groupby("case_id")["input_fingerprint"].nunique(dropna=False)
    checksums_per_case = results.groupby("case_id")["selected_item_ids_checksum"].nunique(dropna=False)
    repeat_groups = results.groupby(
        ["case_id", "algorithm", "random_seed", "input_fingerprint"],
        dropna=False,
    ).size()
    determinism = build_determinism_evidence(results)
    pairwise = build_pairwise_outcomes(results)
    pairwise_vs_baseline = {
        comparator: _outcomes_for_comparator(pairwise, comparator)
        for comparator in CANONICAL_ALGORITHMS
        if comparator != BASELINE_ALGORITHM
    }
    checks = {
        "canonical_corpus_id": manifest.get("corpus_id") == CANONICAL_CORPUS_ID,
        "manifest_status_success": manifest.get("status") == "SUCCESS",
        "case_count_24": results["case_id"].nunique() == EXPECTED_CASE_COUNT,
        "algorithms_exactly_three": tuple(sorted(results["algorithm"].unique()))
        == tuple(sorted(CANONICAL_ALGORITHMS)),
        "execution_count_144": len(results) == EXPECTED_EXECUTION_COUNT,
        "manifest_counts_match": (
            manifest.get("case_count") == EXPECTED_CASE_COUNT
            and manifest.get("execution_count") == EXPECTED_EXECUTION_COUNT
            and manifest.get("successful_execution_count") == EXPECTED_EXECUTION_COUNT
        ),
        "all_success_and_independently_valid": bool(success.all() and valid.all()),
        "one_fingerprint_per_case": bool((fingerprints_per_case == 1).all()),
        "one_item_checksum_per_case": bool((checksums_per_case == 1).all()),
        "repeat_count_two_for_72_groups": bool(
            len(repeat_groups) == EXPECTED_CASE_COUNT * len(CANONICAL_ALGORITHMS)
            and (repeat_groups == EXPECTED_REPEAT_COUNT).all()
        ),
        "deterministic_objective_and_placement": bool(
            len(determinism) == EXPECTED_CASE_COUNT * len(CANONICAL_ALGORITHMS)
            and determinism["deterministic"].map(_as_bool).all()
        ),
        "objective_null_on_failure": failure_objective_is_null,
        "ffd_vs_best_fit_0_24_0": pairwise_vs_baseline["extreme_point_ffd"]
        == {"WIN": 0, "TIE": 24, "LOSS": 0},
        "mes_vs_best_fit_1_22_1": pairwise_vs_baseline["maximal_space_best_fit"]
        == {"WIN": 1, "TIE": 22, "LOSS": 1},
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    case_summary = build_case_algorithm_summary(results)
    differences = build_case_differences(results)
    distribution = build_distribution_summary(results, baseline_algorithm=BASELINE_ALGORITHM)
    return {
        "schema_version": "1.0",
        "level": "level_02",
        "status": status,
        "corpus_id": manifest.get("corpus_id"),
        "source_run": _portable_path(run),
        "source_results_checksum": sha256_file(results_path),
        "baseline_algorithm": BASELINE_ALGORITHM,
        "baseline_is_proven_optimal": False,
        "official_objective": "used_container_count_then_total_container_cost",
        "coverage": {
            "case_count": int(results["case_id"].nunique()),
            "algorithm_count": int(results["algorithm"].nunique()),
            "repeat_count": EXPECTED_REPEAT_COUNT,
            "execution_count": len(results),
            "valid_execution_count": int((success & valid).sum()),
            "deterministic_group_count": int(determinism["deterministic"].map(_as_bool).sum()),
        },
        "checks": checks,
        "paired_outcomes_vs_baseline": pairwise_vs_baseline,
        "quality_conclusion": (
            "FFD hòa Best Fit trên toàn bộ 24 bài; MES có kết quả hỗn hợp với "
            "1 thắng, 22 hòa và 1 thua. Chưa có thuật toán dẫn đầu về chất lượng."
        ),
        "interpretation_limits": [
            "Best Fit là mốc đối chiếu, không phải nghiệm tối ưu đã được chứng minh.",
            "Aggregate lower bound chỉ xét sức chứa tổng hợp, không chứng minh khả thi hình học.",
            "Không lấy trung bình raw container, chi phí hoặc objective giữa các quy mô.",
            "Mỗi nhóm thuật toán–quy mô có 8 lượt chạy nên chưa công bố p95.",
        ],
        "different_cases": _records(differences),
        "case_algorithm_summary": _records(case_summary),
        "distribution_summary": _records(distribution),
    }


def write_canonical_benchmark_evidence(
    report: dict[str, Any], output_prefix: str | Path,
) -> tuple[Path, Path]:
    """Write machine-readable JSON and a Vietnamese, non-technical Markdown report."""
    prefix = Path(output_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = prefix.with_suffix(".json")
    markdown_path = prefix.with_suffix(".md")
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    coverage = report["coverage"]
    ffd = report["paired_outcomes_vs_baseline"]["extreme_point_ffd"]
    mes = report["paired_outcomes_vs_baseline"]["maximal_space_best_fit"]
    lines = [
        "# Evidence benchmark canonical Level 2 — 2026-08-13", "",
        f"- Trạng thái: **{report['status']}**.",
        f"- Phạm vi: **{coverage['case_count']} bài kiểm tra**, "
        f"**{coverage['execution_count']} lượt chạy**.",
        f"- Hợp lệ độc lập: **{coverage['valid_execution_count']}/{coverage['execution_count']}**.",
        f"- Nhóm lặp deterministic: **{coverage['deterministic_group_count']}/72**.",
        "- Mốc đối chiếu: **Extreme Point Best Fit**; đây không phải nghiệm tối ưu đã chứng minh.",
        "", "## Kết luận chất lượng", "",
        report["quality_conclusion"], "",
        "| Thuật toán so với Best Fit | Thắng | Hòa | Thua |",
        "|---|---:|---:|---:|",
        f"| Extreme Point FFD | {ffd['WIN']} | {ffd['TIE']} | {ffd['LOSS']} |",
        f"| Maximal Empty Spaces Best Fit | {mes['WIN']} | {mes['TIE']} | {mes['LOSS']} |",
        "", "## Các bài tạo khác biệt", "",
        "Chỉ các bài mà ít nhất hai thuật toán dùng số container hoặc chi phí khác nhau mới xuất hiện dưới đây.",
        "",
        "| Bài kiểm tra | Số kiện | Thuật toán | Container | Chi phí |",
        "|---|---:|---|---:|---:|",
    ]
    for row in report["different_cases"]:
        lines.append(
            f"| {row['case_id']} | {int(row['item_count'])} | "
            f"{_algorithm_label(row['algorithm'])} | {int(row['used_container_count'])} | "
            f"{float(row['total_container_cost']):.0f} |"
        )
    lines.extend(["", "## Chất lượng theo quy mô", ""])
    lines.extend(_distribution_markdown(report["distribution_summary"]))
    lines.extend(["", "## Giới hạn diễn giải", ""])
    lines.extend(f"- {value}" for value in report["interpretation_limits"])
    lines.extend(["", "## Kiểm tra phát hành", ""])
    lines.extend(
        f"- `{name}`: **{'PASS' if passed else 'FAIL'}**"
        for name, passed in report["checks"].items()
    )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, markdown_path


def _outcomes_for_comparator(pairwise: pd.DataFrame, comparator: str) -> dict[str, int]:
    counts = {"WIN": 0, "TIE": 0, "LOSS": 0}
    for row in pairwise.itertuples(index=False):
        if row.algorithm_a == BASELINE_ALGORITHM and row.algorithm_b == comparator:
            outcome = {"WIN": "LOSS", "LOSS": "WIN"}.get(row.outcome_for_a, row.outcome_for_a)
        elif row.algorithm_b == BASELINE_ALGORITHM and row.algorithm_a == comparator:
            outcome = row.outcome_for_a
        else:
            continue
        if outcome in counts:
            counts[outcome] += 1
    return counts


def _distribution_markdown(records: list[dict[str, Any]]) -> list[str]:
    lines = [
        "Median và min–max dưới đây được tính giữa các bài cùng quy mô, không lấy trung bình raw xuyên quy mô.",
        "", "| Thuật toán | Số kiện | Gap median | Gap min–max | Wall runtime median (s) |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in sorted(records, key=lambda value: (value["item_count"], value["algorithm"])):
        lines.append(
            f"| {_algorithm_label(row['algorithm'])} | {int(row['item_count'])} | "
            f"{float(row['container_gap_lower_bound_median']):.1f} | "
            f"{float(row['container_gap_lower_bound_min']):.1f}–"
            f"{float(row['container_gap_lower_bound_max']):.1f} | "
            f"{float(row['runtime_p50_seconds']):.3f} |"
        )
    return lines


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    return json.loads(frame.to_json(orient="records"))


def _algorithm_label(algorithm: str) -> str:
    return {
        "extreme_point_best_fit": "Extreme Point Best Fit",
        "extreme_point_ffd": "Extreme Point FFD",
        "maximal_space_best_fit": "Maximal Empty Spaces Best Fit",
    }.get(str(algorithm), str(algorithm))


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def _portable_path(path: Path) -> str:
    try:
        return path.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return str(path)
