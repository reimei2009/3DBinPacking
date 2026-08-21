"""Fail-closed evidence evaluator for the repair early-stop research A/B."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import median
from typing import Any

import pandas as pd

from ..provenance import sha256_file


EXPECTED_CORPUS_ID = "level_02_company_like_repair_early_stop_ab_v1"


def evaluate_repair_early_stop_v1(run_dir: str | Path) -> dict[str, Any]:
    source = Path(run_dir).resolve()
    paths = {
        "manifest.json": source / "manifest.json",
        "benchmark/results.csv": source / "benchmark/results.csv",
        "benchmark/determinism_evidence.csv": (
            source / "benchmark/determinism_evidence.csv"
        ),
        "benchmark/repair_early_stop_comparison.csv": (
            source / "benchmark/repair_early_stop_comparison.csv"
        ),
    }
    if not all(path.is_file() for path in paths.values()):
        raise ValueError("Repair evidence requires manifest, results, determinism and comparison")
    try:
        manifest = json.loads(paths["manifest.json"].read_text(encoding="utf-8"))
        results = pd.read_csv(paths["benchmark/results.csv"])
        determinism = pd.read_csv(paths["benchmark/determinism_evidence.csv"])
        comparison = pd.read_csv(paths["benchmark/repair_early_stop_comparison.csv"])
    except (OSError, json.JSONDecodeError, pd.errors.ParserError) as exc:
        raise ValueError(f"Cannot read repair early-stop evidence: {exc}") from exc
    if manifest.get("corpus_id") != EXPECTED_CORPUS_ID:
        raise ValueError("Repair evidence corpus_id mismatch")
    if manifest.get("status") != "SUCCESS" or manifest.get("git_dirty") is not False:
        raise ValueError("Repair evidence requires a successful clean source run")
    required = {
        "success", "validation_valid", "official_objective", "case_id", "algorithm",
    }
    missing = required - set(results.columns)
    if missing:
        raise ValueError("Repair results are missing: " + ", ".join(sorted(missing)))
    success = _bool_series(results["success"])
    valid = _bool_series(results["validation_valid"])
    failed = ~success
    leaked = failed & results["official_objective"].notna()
    if bool(leaked.any()):
        raise ValueError("Failed repair executions must have a null official objective")
    if int(success.sum()) != len(results) or int(valid.sum()) != len(results):
        raise ValueError("Every repair V1 execution must be successful and independently VALID")
    if len(results) != 48 or results["case_id"].nunique() != 8:
        raise ValueError("Repair V1 requires exactly 8 cases and 48 executions")
    if len(determinism) != 16 or not bool(_bool_series(determinism["deterministic"]).all()):
        raise ValueError("Repair V1 deterministic gate failed")
    if len(comparison) != 8:
        raise ValueError("Repair V1 requires exactly 8 paired comparisons")
    outcomes = comparison["quality_outcome"].astype(str)
    unknown = set(outcomes) - {"IMPROVED", "UNCHANGED", "REGRESSION"}
    if unknown:
        raise ValueError("Unknown repair quality outcome: " + ", ".join(sorted(unknown)))
    reductions = pd.to_numeric(comparison["runtime_reduction_ratio"], errors="raise")
    counts = {name: int(outcomes.eq(name).sum()) for name in (
        "IMPROVED", "UNCHANGED", "REGRESSION",
    )}
    regressions = comparison.loc[outcomes.eq("REGRESSION"), [
        "algorithm", "comparison_group", "item_count", "standard_containers",
        "early_stop_containers", "standard_cost", "early_stop_cost",
    ]].to_dict(orient="records")
    return {
        "schema_version": "1.0",
        "evidence_id": "level_02_repair_early_stop_v1_20260821",
        "decision": "NOT_PROMOTED" if counts["REGRESSION"] else "PROMOTION_REVIEW_ALLOWED",
        "reason": (
            "Early-stop reduced runtime but regressed the official objective."
            if counts["REGRESSION"]
            else "No official-objective regression was observed."
        ),
        "source": {
            "run_id": manifest.get("run_id"),
            "run_dir": _portable_run_path(source),
            "corpus_id": manifest.get("corpus_id"),
            "git_commit": manifest.get("git_commit"),
            "git_dirty": manifest.get("git_dirty"),
        },
        "coverage": {
            "case_count": int(results["case_id"].nunique()),
            "execution_count": int(len(results)),
            "valid_execution_count": int(valid.sum()),
            "deterministic_group_count": int(len(determinism)),
            "paired_comparison_count": int(len(comparison)),
        },
        "quality_outcomes": counts,
        "median_runtime_reduction_percent": float(median(reductions) * 100.0),
        "regressions": regressions,
        "artifact_checksums": {
            name: sha256_file(path) for name, path in paths.items()
        },
    }


def render_repair_early_stop_v1_markdown(report: dict[str, Any]) -> str:
    coverage = report["coverage"]
    outcomes = report["quality_outcomes"]
    lines = [
        "# Level 2 — Repair Early-stop V1",
        "",
        "## Kết luận",
        "",
        f"Quyết định chính thức: **{report['decision']}**.",
        "",
        "Early-stop tiết kiệm thời gian đáng kể nhưng làm xấu official objective ở "
        "hai cặp 500 kiện. Vì vậy cơ chế tiếp tục mặc định tắt.",
        "",
        "## Evidence",
        "",
        f"- Coverage: {coverage['case_count']} case / {coverage['execution_count']} lượt; "
        f"{coverage['valid_execution_count']} lượt independently `VALID`.",
        f"- Deterministic: {coverage['deterministic_group_count']}/16 nhóm.",
        f"- Paired outcomes: {outcomes['IMPROVED']} cải thiện / "
        f"{outcomes['UNCHANGED']} không đổi / {outcomes['REGRESSION']} regression.",
        f"- Median runtime reduction: {report['median_runtime_reduction_percent']:.2f}%.",
        f"- Source commit: `{report['source']['git_commit']}`; `git_dirty=false`.",
        "",
        "## Các cặp regression",
        "",
        "| Thuật toán | Case | Repair chuẩn | Early-stop |",
        "|---|---|---:|---:|",
    ]
    for row in report["regressions"]:
        lines.append(
            f"| `{row['algorithm']}` | `{row['comparison_group']}` | "
            f"{int(row['standard_containers'])} container / {row['standard_cost']:.0f} | "
            f"{int(row['early_stop_containers'])} container / {row['early_stop_cost']:.0f} |"
        )
    lines.extend([
        "",
        "Không điều chỉnh threshold chỉ để khớp các case này. Bước tiếp theo là thu thập "
        "timeline improvement bằng diagnostic riêng trước khi cân nhắc V2.",
        "",
        "## Checksums",
        "",
    ])
    lines.extend(
        f"- `{name}`: `{checksum}`"
        for name, checksum in report["artifact_checksums"].items()
    )
    return "\n".join(lines) + "\n"


def _bool_series(values: pd.Series) -> pd.Series:
    def parse(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if pd.isna(value):
            return False
        return str(value).strip().lower() in {"true", "1", "yes"}
    return values.map(parse).astype(bool)


def _portable_run_path(source: Path) -> str:
    parts = source.parts
    try:
        index = next(i for i, value in enumerate(parts) if value.lower() == "outputs")
    except StopIteration:
        return source.name
    return Path(*parts[index:]).as_posix()
