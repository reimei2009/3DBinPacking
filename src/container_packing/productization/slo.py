"""Fail-closed SLO evaluation for company-like shadow benchmark artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from ..benchmarks.distribution import build_determinism_evidence, build_pairwise_outcomes
from ..provenance import sha256_file
from .company_corpus import CompanyCorpusContract


def evaluate_shadow_slo(
    run_dir: str | Path,
    contract: CompanyCorpusContract,
    *,
    ui_response_p95_seconds: float | None = None,
) -> dict[str, Any]:
    source = Path(run_dir).resolve()
    manifest_path = source / "manifest.json"
    results_path = source / "benchmark" / "results.csv"
    determinism_path = source / "benchmark" / "determinism_evidence.csv"
    pairwise_path = source / "benchmark" / "pairwise_outcomes.csv"
    required_artifacts = (manifest_path, results_path, determinism_path, pairwise_path)
    if not all(path.is_file() for path in required_artifacts):
        raise ValueError(
            "Shadow SLO evaluation requires manifest, results, determinism and pairwise artifacts"
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        results = pd.read_csv(results_path)
    except (OSError, json.JSONDecodeError, pd.errors.ParserError) as exc:
        raise ValueError(f"Cannot read shadow benchmark evidence: {exc}") from exc
    return evaluate_shadow_slo_frame(
        results,
        contract,
        manifest=manifest,
        artifact_checksums={
            "manifest.json": sha256_file(manifest_path),
            "benchmark/results.csv": sha256_file(results_path),
            "benchmark/determinism_evidence.csv": sha256_file(determinism_path),
            "benchmark/pairwise_outcomes.csv": sha256_file(pairwise_path),
        },
        ui_response_p95_seconds=ui_response_p95_seconds,
    )


def evaluate_shadow_slo_frame(
    results: pd.DataFrame,
    contract: CompanyCorpusContract,
    *,
    manifest: dict[str, Any] | None = None,
    artifact_checksums: dict[str, str] | None = None,
    ui_response_p95_seconds: float | None = None,
) -> dict[str, Any]:
    required = {
        "level", "success", "status", "validation_status", "objective_value",
        "used_container_count", "total_container_cost", "algorithm", "item_count",
        "input_fingerprint", "case_id", "wall_runtime_seconds", "peak_rss_bytes",
        "placement_signature", "random_seed",
    }
    missing = required - set(results.columns)
    if missing:
        raise ValueError("Shadow results are missing: " + ", ".join(sorted(missing)))
    frame = results.copy()
    frame["success"] = frame["success"].fillna(False).astype(bool)
    failure = ~frame["success"]
    leaked = failure & (
        frame["objective_value"].notna()
        | frame["used_container_count"].notna()
        | frame["total_container_cost"].notna()
    )
    if bool(leaked.any()):
        raise ValueError("Failed shadow executions must not carry an official objective")
    unknown = set(frame["algorithm"].astype(str)) - set(contract.algorithms)
    if unknown:
        raise ValueError("Shadow results contain undeclared algorithms: " + ", ".join(sorted(unknown)))
    successful = frame[frame["success"]]
    if not successful[successful["validation_status"].astype(str).ne("VALID")].empty:
        raise ValueError("Every successful shadow execution must be independently VALID")

    errors: list[str] = []
    rows: list[dict[str, Any]] = []
    runtime_limits = {
        int(key): float(value)
        for key, value in dict(contract.slo["runtime_p95_seconds"]).items()
    }
    minimum_samples = int(contract.slo["minimum_runtime_samples_per_scale"])
    maximum_memory = int(contract.slo["maximum_peak_rss_bytes"])
    for (algorithm, item_count), group in frame.groupby(["algorithm", "item_count"], sort=True):
        runtimes = pd.to_numeric(group["wall_runtime_seconds"], errors="coerce").dropna()
        memories = pd.to_numeric(group["peak_rss_bytes"], errors="coerce").dropna()
        count = int(item_count)
        p95 = None if len(runtimes) < minimum_samples else float(runtimes.quantile(0.95))
        limit = runtime_limits.get(count)
        if p95 is None:
            errors.append(f"{algorithm}/{count}: fewer than {minimum_samples} runtime samples")
        elif limit is None:
            errors.append(f"{algorithm}/{count}: no runtime p95 SLO is declared")
        elif p95 > float(limit):
            errors.append(f"{algorithm}/{count}: runtime p95 {p95:.3f}s exceeds {limit:.3f}s")
        memory_p95 = None if memories.empty else float(memories.quantile(0.95))
        if memory_p95 is not None and memory_p95 > maximum_memory:
            errors.append(f"{algorithm}/{count}: peak RSS p95 exceeds the declared limit")
        rows.append({
            "algorithm": str(algorithm),
            "item_count": count,
            "execution_count": int(len(group)),
            "valid_rate": float(group["success"].mean()),
            "runtime_p50_seconds": None if runtimes.empty else float(runtimes.median()),
            "runtime_p95_seconds": p95,
            "runtime_p95_limit_seconds": limit,
            "peak_rss_p95_bytes": memory_p95,
        })

    valid_rate = float(frame["success"].mean()) if len(frame) else 0.0
    timeout_rate = float(frame["status"].astype(str).eq("TIME_LIMIT").mean()) if len(frame) else 0.0
    invalid_rate = float(
        frame["status"].astype(str).isin({"INVALID_SOLUTION", "VALIDATION_FAILED"}).mean()
    ) if len(frame) else 0.0
    if valid_rate < float(contract.slo["required_valid_rate"]):
        errors.append("valid rate is below the declared SLO")
    if timeout_rate > float(contract.slo["maximum_timeout_rate"]):
        errors.append("timeout rate exceeds the declared SLO")
    if invalid_rate > float(contract.slo["maximum_invalid_rate"]):
        errors.append("invalid rate exceeds the declared SLO")
    ui_limit = float(contract.slo["ui_response_p95_seconds"])
    if ui_response_p95_seconds is None:
        errors.append("UI response p95 evidence is not available")
    elif ui_response_p95_seconds > ui_limit:
        errors.append("UI response p95 exceeds the declared SLO")

    determinism = build_determinism_evidence(frame)
    if determinism.empty or not bool(determinism["deterministic"].all()):
        errors.append("repeat determinism gate failed")
    pairwise = build_pairwise_outcomes(frame)
    return {
        "schema_version": "1.0",
        "corpus_id": contract.corpus_id,
        "evidence_class": contract.evidence_class,
        "production_evidence": False,
        "status": "SHADOW_PASS" if not errors else "SHADOW_NOT_READY",
        "execution_count": int(len(frame)),
        "valid_execution_count": int(frame["success"].sum()),
        "valid_rate": valid_rate,
        "timeout_rate": timeout_rate,
        "invalid_rate": invalid_rate,
        "deterministic_group_count": int(len(determinism)),
        "pairwise_case_count": int(len(pairwise)),
        "runtime_and_memory": rows,
        "ui_response_p95_seconds": ui_response_p95_seconds,
        "ui_response_p95_limit_seconds": ui_limit,
        "manifest": dict(manifest or {}),
        "artifact_checksums": dict(artifact_checksums or {}),
        "errors": errors,
        "safety_statement_vi": contract.safety_statement_vi,
    }


def render_shadow_slo_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Báo cáo SLO shadow cho productization",
        "",
        f"- Trạng thái: **{report['status']}**.",
        f"- Corpus: `{report['corpus_id']}`.",
        f"- Lượt hợp lệ: {report['valid_execution_count']}/{report['execution_count']}.",
        f"- Tỷ lệ timeout: {report['timeout_rate']:.2%}.",
        f"- Phân loại evidence: `{report['evidence_class']}`; không phải production evidence.",
        "",
        "| Thuật toán | Số kiện | Số lượt | Runtime p50 | Runtime p95 | Peak RSS p95 |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in report["runtime_and_memory"]:
        p50 = row["runtime_p50_seconds"]
        p95 = row["runtime_p95_seconds"]
        memory = row["peak_rss_p95_bytes"]
        lines.append(
            f"| {row['algorithm']} | {row['item_count']} | {row['execution_count']} | "
            f"{'—' if p50 is None else f'{p50:.3f}s'} | "
            f"{'Chưa đủ mẫu' if p95 is None else f'{p95:.3f}s'} | "
            f"{'—' if memory is None else f'{memory / 1024 / 1024:.1f} MiB'} |"
        )
    lines.extend(["", "## Gate còn thiếu hoặc không đạt", ""])
    lines.extend([f"- {value}" for value in report["errors"]] or ["- Không có."])
    lines.extend(["", f"> {report['safety_statement_vi']}", ""])
    return "\n".join(lines)
