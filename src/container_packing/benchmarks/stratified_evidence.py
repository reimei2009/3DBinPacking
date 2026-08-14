"""Gate và tổng hợp evidence cho ba tầng benchmark Level 2 V2."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .distribution import build_determinism_evidence, build_pairwise_outcomes


_EXPECTED = {
    "random_distribution": {
        "corpus_id": "level_02_generated_1k_500_random_v2_candidate",
        "case_count": 60,
        "execution_count": 540,
    },
    "stress": {
        "corpus_id": "level_02_generated_1k_500_stress_v2_candidate",
        "case_count": 18,
        "execution_count": 162,
    },
    "prefix_regression": {
        "corpus_id": "level_02_generated_1k_500_prefix_regression_v2",
        "case_count": 6,
        "execution_count": 54,
    },
}
_ALGORITHMS = {
    "extreme_point_best_fit", "extreme_point_ffd", "maximal_space_best_fit",
}


def _read_run(
    run_dir: Path, stratum: str, expected: dict[str, Any], *, expected_algorithms: set[str], repeats: int,
) -> tuple[dict[str, Any], pd.DataFrame]:
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    results = pd.read_csv(run_dir / "benchmark/results.csv")
    errors: list[str] = []
    if manifest.get("corpus_id") != expected["corpus_id"]:
        errors.append("corpus_id không khớp")
    if int(manifest.get("case_count", -1)) != expected["case_count"]:
        errors.append("số bài kiểm tra không khớp")
    if len(results) != expected["execution_count"]:
        errors.append("số lượt chạy không khớp")
    if set(results.get("benchmark_stratum", pd.Series(dtype=str)).dropna()) != {stratum}:
        errors.append("tầng benchmark trong kết quả không khớp")
    success = results["success"].fillna(False).astype(bool)
    if not success.all():
        errors.append("có lượt chạy không thành công")
    if "validation_valid" not in results or not results["validation_valid"].fillna(False).astype(bool).all():
        errors.append("có lượt chạy chưa independently VALID")
    failed_objective = (~success) & results.get(
        "objective_value", pd.Series(index=results.index, dtype=float),
    ).notna()
    if failed_objective.any():
        errors.append("lượt thất bại vẫn có objective")
    for _, group in results.groupby("case_id", sort=True):
        case_id = str(group["case_id"].iloc[0])
        if group["input_fingerprint"].nunique() != 1:
            errors.append(f"case {case_id} có nhiều input fingerprint")
            break
        if set(group["algorithm"].astype(str)) != expected_algorithms:
            errors.append(f"case {case_id} không có đúng ba thuật toán")
            break
        if group.groupby("algorithm", sort=False).size().to_dict() != {
            algorithm: repeats for algorithm in group["algorithm"].drop_duplicates()
        }:
            errors.append(f"case {case_id} không có đúng ba repeat cho mỗi thuật toán")
            break
        if (
            "selected_item_ids_checksum" not in group
            or group["selected_item_ids_checksum"].nunique() != 1
        ):
            errors.append(f"case {case_id} không dùng cùng tập item giữa các thuật toán")
            break
    determinism = build_determinism_evidence(results)
    if len(determinism) != expected["case_count"] * 3:
        errors.append("số nhóm deterministic không khớp")
    elif not determinism["deterministic"].fillna(False).all():
        errors.append("objective hoặc placement signature không deterministic")
    return {
        "stratum": stratum,
        "run_dir": run_dir.as_posix(),
        "corpus_id": manifest.get("corpus_id"),
        "case_count": int(results["case_id"].nunique()),
        "execution_count": len(results),
        "valid_execution_count": int(results["validation_valid"].fillna(False).sum()),
        "deterministic_group_count": int(determinism["deterministic"].fillna(False).sum()),
        "errors": errors,
        "passed": not errors,
    }, results


def build_stratified_evidence_for_protocol(
    run_dirs: dict[str, Path], *, level_id: str, expected: dict[str, dict[str, Any]],
    report_id: str, repeats: int = 3,
) -> dict[str, Any]:
    """Build stratified evidence for any level sharing the canonical V2 protocol."""
    if set(run_dirs) != set(expected):
        raise ValueError("Evidence requires random_distribution, stress and prefix_regression runs")
    strata: list[dict[str, Any]] = []
    frames: dict[str, pd.DataFrame] = {}
    for stratum in expected:
        evidence, results = _read_run(
            Path(run_dirs[stratum]), stratum, expected[stratum],
            expected_algorithms=_ALGORITHMS, repeats=repeats,
        )
        strata.append(evidence)
        frames[stratum] = results
    random_outcomes = build_pairwise_outcomes(frames["random_distribution"])
    pairwise = []
    baseline = "extreme_point_best_fit"
    for comparator in ("extreme_point_ffd", "maximal_space_best_fit"):
        rows = random_outcomes[
            random_outcomes[["algorithm_a", "algorithm_b"]].apply(
                lambda row: {str(row.iloc[0]), str(row.iloc[1])} == {baseline, comparator},
                axis=1,
            )
        ]
        outcomes = []
        for row in rows.itertuples(index=False):
            value = str(row.outcome_for_a)
            if str(row.algorithm_a) == baseline:
                value = {"WIN": "LOSS", "LOSS": "WIN"}.get(value, value)
            outcomes.append(value)
        pairwise.append({
            "comparator": comparator,
            "wins": outcomes.count("WIN"),
            "ties": outcomes.count("TIE"),
            "losses": outcomes.count("LOSS"),
        })
    passed = all(value["passed"] for value in strata)
    return {
        "schema_version": "1.0",
        "report_id": report_id,
        "level_id": level_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if passed else "FAIL",
        "promotion_to_canonical_allowed": passed,
        "case_count": sum(value["case_count"] for value in strata),
        "execution_count": sum(value["execution_count"] for value in strata),
        "strata": strata,
        "random_distribution_pairwise_vs_best_fit": pairwise,
        "interpretation": {
            "random_distribution": "Nguồn chính cho kết luận chất lượng tổng quát.",
            "stress": "Báo riêng; không trộn vào tỷ lệ thắng của random.",
            "prefix_regression": "Chỉ phát hiện hồi quy theo thứ tự nguồn.",
        },
    }


def build_stratified_evidence(run_dirs: dict[str, Path]) -> dict[str, Any]:
    """Backward-compatible Level 2 V2 evidence builder."""
    return build_stratified_evidence_for_protocol(
        run_dirs,
        level_id="level_02",
        expected=_EXPECTED,
        report_id="level_02_stratified_benchmark_v2_candidate",
    )


def write_stratified_evidence(
    report: dict[str, Any], output_prefix: Path,
) -> tuple[Path, Path]:
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = output_prefix.with_suffix(".json")
    markdown_path = output_prefix.with_suffix(".md")
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    lines = [
        "# Benchmark Level 2 V2 phân tầng",
        "",
        f"- Trạng thái: `{report['status']}`",
        f"- Tổng số bài: {report['case_count']}",
        f"- Tổng lượt chạy: {report['execution_count']}",
        "",
        "Ba tầng được báo riêng; stress và prefix không tham gia kết luận phân phối random.",
        "",
        "## Gate từng tầng",
        "",
    ]
    for value in report["strata"]:
        lines.append(
            f"- `{value['stratum']}`: {'PASS' if value['passed'] else 'FAIL'} — "
            f"{value['case_count']} bài, {value['execution_count']} lượt."
        )
    lines.extend(["", "## So sánh trên phân phối random", ""])
    for value in report["random_distribution_pairwise_vs_best_fit"]:
        lines.append(
            f"- `{value['comparator']}`: {value['wins']} thắng / "
            f"{value['ties']} hòa / {value['losses']} thua so với Best Fit."
        )
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, markdown_path
