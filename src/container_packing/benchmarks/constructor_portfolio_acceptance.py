"""Fail-closed evidence gate for the Level 4-5 constructor portfolio."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
import json

import pandas as pd

from ..provenance import sha256_file
from ..reporting import write_json, write_text


PORTFOLIO_ALGORITHM = "validated_best_fit_mes_portfolio"
BEST_FIT_ALGORITHM = "extreme_point_best_fit"
SOURCE_COMMIT = "7a26ea157af0309eb61e764c9540ca7f6e66bf52"
EXPECTED_STRATA = {
    "random": (60, 180),
    "stress": (18, 54),
    "prefix": (6, 18),
}
DEADLINES_BY_ITEM_COUNT = {20: 30.0, 50: 30.0, 100: 60.0, 200: 120.0, 300: 120.0, 500: 180.0}


def evaluate_constructor_portfolio_acceptance(
    portfolio_runs: Sequence[str | Path],
    baseline_runs: Sequence[str | Path],
    *,
    expected_checksums: Mapping[str, Mapping[str, str]] | None = None,
) -> dict[str, Any]:
    """Evaluate immutable portfolio artifacts and fail closed on missing evidence."""
    errors: list[str] = []
    sources: list[dict[str, Any]] = []
    baseline_sources: list[dict[str, Any]] = []
    portfolio_by_level: dict[str, list[tuple[dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame]]] = {
        "level_04": [], "level_05": [],
    }
    baseline_by_level: dict[str, list[pd.DataFrame]] = {"level_04": [], "level_05": []}

    for value in portfolio_runs:
        loaded = _load_portfolio_run(Path(value), expected_checksums, errors)
        if loaded is None:
            continue
        manifest, results, comparison, determinism, source = loaded
        level = str(manifest.get("level"))
        if level not in portfolio_by_level:
            errors.append(f"unsupported portfolio level: {level}")
            continue
        portfolio_by_level[level].append((manifest, results, comparison, determinism))
        sources.append(source)

    for value in baseline_runs:
        loaded = _load_baseline_run(Path(value), errors)
        if loaded is None:
            continue
        level, results, source = loaded
        if level in baseline_by_level:
            baseline_by_level[level].append(results)
            baseline_sources.append(source)
        else:
            errors.append(f"unsupported baseline level: {level}")

    levels: dict[str, Any] = {}
    for level in ("level_04", "level_05"):
        level_report = _evaluate_level(
            level, portfolio_by_level[level], baseline_by_level[level], errors,
        )
        levels[level] = level_report

    overall_promoted = not errors and all(
        value["status"] == "PASS" for value in levels.values()
    )
    return {
        "schema_version": "1.0",
        "report_id": "level_04_05_validated_constructor_portfolio_v1",
        "status": "PROMOTED" if overall_promoted else "NOT_PROMOTED",
        "portfolio_ui_qualified": overall_promoted,
        "source_commit_required": SOURCE_COMMIT,
        "official_objective": "used_container_count_then_total_container_cost",
        "levels": levels,
        "source_evidence": sources,
        "baseline_source_evidence": baseline_sources,
        "errors": sorted(set(errors)),
        "interpretation": [
            "success_rate=1.0 only proves that the final selected solution was valid.",
            "Promotion additionally requires deterministic output and the bounded runtime gate.",
            "Level 4 and Level 5 must both pass; partial rollout is not allowed by this protocol.",
        ],
    }


def write_constructor_portfolio_acceptance(
    report: dict[str, Any], output_prefix: str | Path,
) -> tuple[Path, Path]:
    """Publish versioned evidence without changing any source run directory."""
    prefix = Path(output_prefix).resolve()
    write_json(prefix.with_suffix(".json"), report)
    write_text(prefix.with_suffix(".md"), _markdown(report))
    return prefix.with_suffix(".json"), prefix.with_suffix(".md")


def _load_portfolio_run(
    run: Path,
    expected_checksums: Mapping[str, Mapping[str, str]] | None,
    errors: list[str],
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]] | None:
    run = run.resolve()
    paths = {
        "manifest.json": run / "manifest.json",
        "results.csv": run / "benchmark" / "results.csv",
        "constructor_portfolio_comparison.csv": run / "benchmark" / "constructor_portfolio_comparison.csv",
        "determinism_evidence.csv": run / "benchmark" / "determinism_evidence.csv",
    }
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        errors.append(f"portfolio artifact incomplete for {run.name}: {', '.join(missing)}")
        return None
    checksums = {name: sha256_file(path) for name, path in paths.items()}
    locked = (expected_checksums or {}).get(run.name)
    if locked is not None:
        for name, expected in locked.items():
            if checksums.get(name) != str(expected).lower():
                errors.append(f"checksum mismatch for {run.name}/{name}")
    try:
        manifest = json.loads(paths["manifest.json"].read_text(encoding="utf-8"))
        results = pd.read_csv(paths["results.csv"], encoding="utf-8-sig")
        comparison = pd.read_csv(paths["constructor_portfolio_comparison.csv"], encoding="utf-8-sig")
        determinism = pd.read_csv(paths["determinism_evidence.csv"], encoding="utf-8-sig")
    except (ValueError, OSError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        errors.append(f"cannot read portfolio artifact {run.name}: {type(exc).__name__}: {exc}")
        return None
    source = {
        "run_id": manifest.get("run_id", run.name),
        "level": manifest.get("level"),
        "corpus_id": manifest.get("corpus_id"),
        "git_commit": manifest.get("git_commit"),
        "git_dirty": bool(manifest.get("git_dirty", False)),
        "checksums": checksums,
    }
    return manifest, results, comparison, determinism, source


def _load_baseline_run(
    run: Path, errors: list[str],
) -> tuple[str, pd.DataFrame, dict[str, Any]] | None:
    manifest_path = run.resolve() / "manifest.json"
    results_path = run.resolve() / "benchmark" / "results.csv"
    if not manifest_path.is_file() or not results_path.is_file():
        errors.append(f"baseline artifact incomplete for {run.name}")
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        results = pd.read_csv(results_path, encoding="utf-8-sig")
    except (ValueError, OSError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        errors.append(f"cannot read baseline artifact {run.name}: {type(exc).__name__}: {exc}")
        return None
    return str(manifest.get("level")), results, {
        "run_id": manifest.get("run_id", run.name),
        "level": manifest.get("level"),
        "corpus_id": manifest.get("corpus_id"),
        "manifest_sha256": sha256_file(manifest_path),
        "results_sha256": sha256_file(results_path),
    }


def _evaluate_level(
    level: str,
    runs: list[tuple[dict[str, Any], pd.DataFrame, pd.DataFrame, pd.DataFrame]],
    baseline_frames: list[pd.DataFrame],
    global_errors: list[str],
) -> dict[str, Any]:
    errors: list[str] = []
    if len(runs) != 3:
        errors.append(f"{level}: expected three portfolio strata, found {len(runs)}")
    observed_strata: set[str] = set()
    results_frames: list[pd.DataFrame] = []
    comparison_frames: list[pd.DataFrame] = []
    determinism_frames: list[pd.DataFrame] = []
    for manifest, results, comparison, determinism in runs:
        corpus_id = str(manifest.get("corpus_id", ""))
        stratum = next((name for name in EXPECTED_STRATA if f"_{name}_v1" in corpus_id), "")
        if not stratum:
            errors.append(f"{level}: unexpected corpus_id {corpus_id}")
        elif stratum in observed_strata:
            errors.append(f"{level}: duplicate stratum {stratum}")
        else:
            observed_strata.add(stratum)
            expected_cases, expected_rows = EXPECTED_STRATA[stratum]
            if results.get("case_id", pd.Series(dtype=object)).nunique() != expected_cases:
                errors.append(f"{level}/{stratum}: case count mismatch")
            if len(results) != expected_rows:
                errors.append(f"{level}/{stratum}: execution count mismatch")
        if manifest.get("status") != "SUCCESS":
            errors.append(f"{level}/{stratum}: manifest status is not SUCCESS")
        if manifest.get("git_commit") != SOURCE_COMMIT or bool(manifest.get("git_dirty", False)):
            errors.append(f"{level}/{stratum}: source must be clean commit {SOURCE_COMMIT}")
        results_frames.append(results)
        comparison_frames.append(comparison)
        determinism_frames.append(determinism)
    if observed_strata != set(EXPECTED_STRATA):
        errors.append(f"{level}: portfolio strata are incomplete")

    results = _concat(results_frames)
    comparison = _concat(comparison_frames)
    determinism = _concat(determinism_frames)
    required_results = {
        "case_id", "algorithm", "repeat", "success", "validation_valid", "status",
        "official_objective", "objective_value", "used_container_count",
        "total_container_cost", "placement_signature", "input_fingerprint",
        "selected_item_ids_checksum", "item_count", "wall_runtime_seconds", "peak_rss_bytes",
    }
    required_comparison = {
        "case_id", "repeat", "selected_matches_best_child", "outcome_vs_best_fit",
        "runtime_ratio_vs_best_fit", "best_fit_validation", "mes_validation",
        "mes_used_container_count", "mes_total_container_cost", "incumbent_preserved",
    }
    if not required_results.issubset(results.columns):
        errors.append(f"{level}: results columns are incomplete")
    if not required_comparison.issubset(comparison.columns):
        errors.append(f"{level}: comparison columns are incomplete")
    if not {"case_id", "deterministic"}.issubset(determinism.columns):
        errors.append(f"{level}: determinism evidence columns are incomplete")

    execution_count = len(results)
    case_count = int(results["case_id"].nunique()) if "case_id" in results else 0
    success = results.get("success", pd.Series(False, index=results.index)).map(_as_bool)
    valid = results.get("validation_valid", pd.Series(False, index=results.index)).map(_as_bool)
    if execution_count != 252 or case_count != 84:
        errors.append(f"{level}: expected 84 cases/252 executions, found {case_count}/{execution_count}")
    if set(results.get("algorithm", pd.Series(dtype=str)).astype(str)) != {PORTFOLIO_ALGORITHM}:
        errors.append(f"{level}: results contain an unexpected algorithm")
    if not bool((success & valid).all()):
        errors.append(f"{level}: every final result must be independently VALID")
    failed = ~success
    objective_columns = [value for value in (
        "official_objective", "objective_value", "used_container_count", "total_container_cost",
    ) if value in results]
    if bool(failed.any()) and bool(results.loc[failed, objective_columns].notna().any(axis=None)):
        errors.append(f"{level}: failed final rows carry an official objective")
    if "input_fingerprint" in results and bool((results.groupby("case_id")["input_fingerprint"].nunique(dropna=False) != 1).any()):
        errors.append(f"{level}: input fingerprint mismatch inside a case")
    repeat_groups = results.groupby("case_id").size() if "case_id" in results else pd.Series(dtype=int)
    if len(repeat_groups) != 84 or not bool((repeat_groups == 3).all()):
        errors.append(f"{level}: every case must have exactly three repeats")

    deterministic_count = 0
    if "deterministic" in determinism:
        deterministic_values = determinism["deterministic"].map(_as_bool)
        deterministic_count = int(deterministic_values.sum())
        if len(determinism) != 84 or not bool(deterministic_values.all()):
            errors.append(f"{level}: deterministic gate failed ({deterministic_count}/84)")

    selected_best = comparison.get("selected_matches_best_child", pd.Series(False, index=comparison.index)).map(_as_bool)
    incumbent_preserved = comparison.get("incumbent_preserved", pd.Series(False, index=comparison.index)).map(_as_bool)
    if len(comparison) != 252 or not bool(selected_best.all()):
        errors.append(f"{level}: selected objective is not always the best valid child")
    outcomes = comparison.get("outcome_vs_best_fit", pd.Series(dtype=str)).astype(str)
    if outcomes.isin({"LOSS", "REGRESSION"}).any():
        errors.append(f"{level}: portfolio has an objective loss")
    if not bool(incumbent_preserved.all()):
        errors.append(f"{level}: a later constructor lost the validated incumbent")
    invalid_mes = ~comparison.get("mes_validation", pd.Series(dtype=str)).astype(str).eq("VALID")
    if bool(invalid_mes.any()):
        mes_objective_present = comparison.loc[invalid_mes, [
            "mes_used_container_count", "mes_total_container_cost",
        ]].notna().any(axis=1)
        if bool(mes_objective_present.any()):
            errors.append(f"{level}: invalid/incomplete MES child carries an objective")

    runtime_ratio = pd.to_numeric(comparison.get("runtime_ratio_vs_best_fit"), errors="coerce")
    runtime_ratio_median = _finite(runtime_ratio.median())
    if runtime_ratio.isna().any() or runtime_ratio_median is None or runtime_ratio_median > 1.8:
        errors.append(f"{level}: median runtime ratio exceeds 1.8")
    runtime_by_scale: dict[str, Any] = {}
    deadline_overshoot_count = 0
    p95_deadline_pass = True
    for item_count, deadline in DEADLINES_BY_ITEM_COUNT.items():
        values = pd.to_numeric(
            results.loc[pd.to_numeric(results.get("item_count"), errors="coerce").eq(item_count), "wall_runtime_seconds"],
            errors="coerce",
        )
        p95 = _finite(values.quantile(0.95))
        maximum = _finite(values.max())
        overshoots = int((values > deadline).sum())
        deadline_overshoot_count += overshoots
        if p95 is None or p95 > deadline:
            p95_deadline_pass = False
        runtime_by_scale[str(item_count)] = {
            "median_seconds": _finite(values.median()), "p95_seconds": p95,
            "max_seconds": maximum, "deadline_seconds": deadline,
            "deadline_overshoot_count": overshoots,
        }
    if not p95_deadline_pass:
        errors.append(f"{level}: runtime p95 exceeds its scale deadline")

    baseline = _concat(baseline_frames)
    baseline_best_fit = baseline[
        baseline.get("algorithm", pd.Series(dtype=str)).astype(str).eq(BEST_FIT_ALGORITHM)
    ].copy() if not baseline.empty else baseline
    portfolio_checksums = set(results.get("selected_item_ids_checksum", pd.Series(dtype=str)).dropna().astype(str))
    baseline_checksums = set(baseline_best_fit.get("selected_item_ids_checksum", pd.Series(dtype=str)).dropna().astype(str))
    if len(baseline_best_fit) != 252 or portfolio_checksums != baseline_checksums:
        errors.append(f"{level}: accepted Best Fit memory baseline is not paired to all 84 inputs")
    portfolio_memory = pd.to_numeric(results.get("peak_rss_bytes"), errors="coerce")
    baseline_memory = pd.to_numeric(baseline_best_fit.get("peak_rss_bytes"), errors="coerce")
    memory_median_overhead = _ratio_overhead(portfolio_memory.median(), baseline_memory.median())
    memory_p95_overhead = _ratio_overhead(portfolio_memory.quantile(.95), baseline_memory.quantile(.95))
    if (
        memory_median_overhead is None or memory_p95_overhead is None
        or memory_median_overhead > 0.20 or memory_p95_overhead > 0.20
    ):
        errors.append(f"{level}: peak-memory overhead exceeds 20%")

    wins = int(outcomes.eq("WIN").sum())
    winning_cases = int(
        comparison.assign(_win=outcomes.eq("WIN")).groupby("case_id")["_win"].median().gt(0.5).sum()
    ) if "case_id" in comparison else 0
    savings = pd.to_numeric(comparison.get("best_fit_used_container_count"), errors="coerce") - pd.to_numeric(
        comparison.get("selected_used_container_count"), errors="coerce",
    )
    median_case_savings = float(comparison.assign(_saved=savings).groupby("case_id")["_saved"].median().sum()) if "case_id" in comparison else 0.0
    if wins == 0:
        errors.append(f"{level}: portfolio produced no objective win")

    global_errors.extend(errors)
    return {
        "status": "PASS" if not errors else "FAIL",
        "coverage": {
            "case_count": case_count, "execution_count": execution_count,
            "valid_execution_count": int((success & valid).sum()),
            "deterministic_group_count": deterministic_count,
        },
        "quality": {
            "win_execution_count": wins,
            "tie_execution_count": int(outcomes.eq("TIE").sum()),
            "loss_execution_count": int(outcomes.eq("LOSS").sum()),
            "winning_case_count_by_median": winning_cases,
            "containers_saved_across_case_medians": median_case_savings,
            "selected_matches_best_child_count": int(selected_best.sum()),
        },
        "runtime": {
            "median_ratio_vs_best_fit_child": runtime_ratio_median,
            "p95_within_deadline": p95_deadline_pass,
            "deadline_overshoot_execution_count": deadline_overshoot_count,
            "by_item_count": runtime_by_scale,
        },
        "memory": {
            "median_overhead_ratio": memory_median_overhead,
            "p95_overhead_ratio": memory_p95_overhead,
        },
        "child_evidence": {
            "best_fit_valid_count": int(comparison.get("best_fit_validation", pd.Series(dtype=str)).astype(str).eq("VALID").sum()),
            "mes_valid_count": int(comparison.get("mes_validation", pd.Series(dtype=str)).astype(str).eq("VALID").sum()),
            "mes_not_run_count": int(comparison.get("mes_validation", pd.Series(dtype=str)).astype(str).eq("NOT_RUN").sum()),
            "incumbent_preserved_count": int(incumbent_preserved.sum()),
        },
        "errors": errors,
    }


def _concat(frames: Iterable[pd.DataFrame]) -> pd.DataFrame:
    values = list(frames)
    return pd.concat(values, ignore_index=True) if values else pd.DataFrame()


def _ratio_overhead(value: Any, baseline: Any) -> float | None:
    value_number = _finite(value)
    baseline_number = _finite(baseline)
    if value_number is None or baseline_number is None or baseline_number <= 0:
        return None
    return value_number / baseline_number - 1.0


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if pd.notna(number) and number not in (float("inf"), float("-inf")) else None


def _as_bool(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"true", "1", "yes"}


def _markdown(report: dict[str, Any]) -> str:
    level4 = report["levels"]["level_04"]
    level5 = report["levels"]["level_05"]
    lines = [
        "# Evidence Constructor Portfolio Level 4–5 — 2026-08-20", "",
        f"- Quyết định: **{report['status']}**.",
        "- Portfolio thử Best Fit và MES trong cùng request rồi chỉ giữ nghiệm hợp lệ tốt hơn.",
        "- `success_rate=1.0` chỉ xác nhận nghiệm cuối hợp lệ; nó không tự động đồng nghĩa đủ điều kiện promotion.",
        "", "## Kết quả gate", "",
        "| Level | VALID | Deterministic | WIN theo lượt | Runtime median / Best Fit | Memory p95 | Trạng thái |",
        "|---|---:|---:|---:|---:|---:|---|",
        _level_row("Level 4", level4),
        _level_row("Level 5", level5),
        "", "## Kết luận", "",
        "Level 4 đạt gate riêng. Level 5 không đạt vì chỉ có 83/84 nhóm deterministic và runtime median bằng 2,219 lần Best Fit, vượt trần 1,8 lần.",
        "Theo protocol đã khóa, cả hai Level phải cùng đạt. Portfolio vì vậy không được mở trên UI, không trở thành mặc định và không được đưa vào `develop`.",
        "", "## Bài Level 5 không deterministic", "",
        "- Input: stable-random seed 307, 500 kiện, repeat 3.",
        "- MES trả `TIME_LIMIT`; Best Fit incumbent hợp lệ được giữ.",
        "- Wall runtime khoảng 1.061 giây so với deadline 180 giây.",
        "- Hai repeat đầu chọn MES với 20 container; repeat 3 giữ Best Fit với 22 container.",
        "", "## Provenance", "",
        f"- Commit nguồn sạch: `{report['source_commit_required']}`.",
    ]
    for source in report["source_evidence"]:
        lines.append(f"- `{source['run_id']}`:")
        for name, checksum in source["checksums"].items():
            lines.append(f"  - `{name}` SHA-256: `{checksum}`")
    lines.append("- Baseline memory được khóa từ các run phân phối đã nghiệm thu:")
    for source in report["baseline_source_evidence"]:
        lines.append(
            f"  - `{source['run_id']}`: manifest `{source['manifest_sha256']}`, "
            f"results `{source['results_sha256']}`."
        )
    lines.extend(["", "## Lỗi gate", ""])
    lines.extend(f"- {value}" for value in report["errors"])
    return "\n".join(lines) + "\n"


def _level_row(label: str, value: dict[str, Any]) -> str:
    coverage = value["coverage"]
    quality = value["quality"]
    runtime = value["runtime"]
    memory = value["memory"]
    return (
        f"| {label} | {coverage['valid_execution_count']}/{coverage['execution_count']} | "
        f"{coverage['deterministic_group_count']}/84 | {quality['win_execution_count']} | "
        f"{runtime['median_ratio_vs_best_fit_child']:.3f}× | "
        f"{memory['p95_overhead_ratio'] * 100:.2f}% | **{value['status']}** |"
    )
