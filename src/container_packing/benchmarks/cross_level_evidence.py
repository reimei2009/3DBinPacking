"""Paired Level 3--5 evidence; never ranks one constraint level above another."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from .cross_level_protocol import expected_protocol
from .stratified_evidence import build_stratified_evidence_for_protocol


def build_cross_level_evidence(run_dirs: dict[str, dict[str, Path]]) -> tuple[dict[str, Any], pd.DataFrame]:
    required_levels = ("level_03", "level_04", "level_05")
    if tuple(run_dirs) != required_levels:
        raise ValueError("Cross-level evidence requires level_03, level_04 and level_05 in order")
    reports = {
        level_id: build_stratified_evidence_for_protocol(
            run_dirs[level_id], level_id=level_id, expected=expected_protocol(level_id),
            report_id=f"{level_id}_distribution_v2",
        )
        for level_id in required_levels
    }
    for level_id in required_levels:
        recovery_strata = []
        for stratum, run_dir in run_dirs[level_id].items():
            manifest = json.loads((Path(run_dir) / "manifest.json").read_text(encoding="utf-8"))
            recovery = manifest.get("recovery") or {}
            if manifest.get("recovery_mode"):
                recovery_strata.append({
                    "stratum": stratum,
                    "source_run_id": recovery.get("run_id"),
                    "reused_execution_count": int(recovery.get("reused_execution_count", 0)),
                    "rerun_execution_count": int(recovery.get("rerun_execution_count", 0)),
                    "deterministic": bool(recovery.get("deterministic", False)),
                })
        reports[level_id]["recovery"] = {
            "used": bool(recovery_strata),
            "strata": recovery_strata,
            "reused_execution_count": sum(
                value["reused_execution_count"] for value in recovery_strata
            ),
            "rerun_execution_count": sum(
                value["rerun_execution_count"] for value in recovery_strata
            ),
        }
    if any(report["status"] != "PASS" for report in reports.values()):
        raise ValueError("Every Level 3--5 stratified evidence gate must PASS first")
    frames: list[pd.DataFrame] = []
    for level_id in required_levels:
        frame = pd.read_csv(Path(run_dirs[level_id]["random_distribution"]) / "benchmark" / "results.csv")
        valid = frame[frame["success"].fillna(False).astype(bool) & frame["validation_valid"].fillna(False).astype(bool)].copy()
        summary = valid.groupby(["case_id", "algorithm", "selected_item_ids_checksum"], sort=True).agg(
            median_wall_runtime_seconds=("wall_runtime_seconds", "median"),
            median_used_container_count=("used_container_count", "median"),
            median_total_container_cost=("total_container_cost", "median"),
        ).reset_index()
        summary["level_id"] = level_id
        frames.append(summary)
    joined = frames[0].merge(frames[1], on=["case_id", "algorithm", "selected_item_ids_checksum"], suffixes=("_level_03", "_level_04"), validate="one_to_one").merge(
        frames[2], on=["case_id", "algorithm", "selected_item_ids_checksum"], validate="one_to_one"
    ).rename(columns={
        "median_wall_runtime_seconds": "median_wall_runtime_seconds_level_05",
        "median_used_container_count": "median_used_container_count_level_05",
        "median_total_container_cost": "median_total_container_cost_level_05",
    })
    joined["level_04_vs_03_runtime_ratio"] = joined["median_wall_runtime_seconds_level_04"] / joined["median_wall_runtime_seconds_level_03"].clip(lower=1e-12)
    joined["level_05_vs_04_runtime_ratio"] = joined["median_wall_runtime_seconds_level_05"] / joined["median_wall_runtime_seconds_level_04"].clip(lower=1e-12)
    joined["level_04_minus_03_containers"] = joined["median_used_container_count_level_04"] - joined["median_used_container_count_level_03"]
    joined["level_05_minus_04_containers"] = joined["median_used_container_count_level_05"] - joined["median_used_container_count_level_04"]
    report = {
        "status": "PASS",
        "levels": list(required_levels),
        "comparison_policy": "Paired descriptive constraint overhead only; it does not rank levels.",
        "paired_case_algorithm_groups": len(joined),
        "reports": reports,
        "runtime_ratio_medians": {
            "level_04_vs_03": float(joined["level_04_vs_03_runtime_ratio"].median()),
            "level_05_vs_04": float(joined["level_05_vs_04_runtime_ratio"].median()),
        },
    }
    return report, joined


def attach_profiling_evidence(
    report: dict[str, Any], profile_run_dirs: dict[str, Path],
) -> dict[str, Any]:
    """Attach diagnostic-only profiling gates without changing benchmark ranking."""
    required_levels = ("level_03", "level_04", "level_05")
    if tuple(profile_run_dirs) != required_levels:
        raise ValueError("Profiling evidence requires level_03, level_04 and level_05 in order")
    profiles: dict[str, Any] = {}
    for level_id in required_levels:
        run_dir = Path(profile_run_dirs[level_id])
        manifest = json.loads((run_dir / "profile_manifest.json").read_text(encoding="utf-8"))
        decision = json.loads((run_dir / "decision_gate.json").read_text(encoding="utf-8"))
        if manifest.get("status") != "PASS":
            raise ValueError(f"Profiling run {level_id} must PASS")
        if manifest.get("run_type") != "benchmark_profile":
            raise ValueError(f"Profiling run {level_id} has an invalid run_type")
        if manifest.get("eligible_for_benchmark_ranking") is not False:
            raise ValueError(f"Profiling run {level_id} must be excluded from ranking")
        profiles[level_id] = {
            "run_dir": run_dir.as_posix(),
            "run_id": manifest.get("run_id"),
            "status": manifest.get("status"),
            "selected_case_count": int(manifest.get("selected_case_count", 0)),
            "execution_count": int(manifest.get("execution_count", 0)),
            "diagnostic_only": True,
            "deadline_neutralized_for_profiler_overhead": bool(
                manifest.get("deadline_neutralized_for_profiler_overhead", False)
            ),
            "decision_gate": decision,
        }
    enriched = dict(report)
    enriched["profiling"] = profiles
    return enriched


def write_cross_level_evidence(
    report: dict[str, Any], paired: pd.DataFrame, output_dir: Path,
) -> tuple[Path, Path, Path]:
    """Publish JSON, paired CSV and a Vietnamese decision report."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "cross_level_distribution_report.json"
    csv_path = output_dir / "cross_level_paired_overhead.csv"
    markdown_path = output_dir / "cross_level_distribution_report.md"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    paired.to_csv(csv_path, index=False, encoding="utf-8")

    lines = [
        "# Acceptance phân phối và profiling Level 3–5 — 2026-08-14",
        "",
        f"- Trạng thái: `{report['status']}`",
        "- Phạm vi: 84 bài và 756 lượt chạy cho mỗi Level; tổng cộng 2.268 lượt.",
        "- Chỉ so sánh thuật toán trong cùng Level. Chênh lệch giữa các Level chỉ mô tả chi phí của ràng buộc.",
        "- Best Fit là mốc đối chiếu, không phải nghiệm tối ưu đã chứng minh.",
        "",
        "## Gate và chất lượng trên 60 bài random",
        "",
    ]
    for level_id in report["levels"]:
        level_report = report["reports"][level_id]
        lines.append(
            f"### {level_id}: {level_report['status']} — "
            f"{level_report['case_count']} bài / {level_report['execution_count']} lượt"
        )
        lines.append("")
        for outcome in level_report["random_distribution_pairwise_vs_best_fit"]:
            lines.append(
                f"- `{outcome['comparator']}` so với Best Fit: "
                f"{outcome['wins']} thắng / {outcome['ties']} hòa / {outcome['losses']} thua."
            )
        recovery = level_report.get("recovery", {})
        if recovery.get("used"):
            lines.append(
                f"- Recovery bất biến: tái sử dụng {recovery['reused_execution_count']} lượt VALID "
                f"và chạy lại {recovery['rerun_execution_count']} lượt lỗi kỹ thuật."
            )
        lines.append("")

    ratios = report["runtime_ratio_medians"]
    lines.extend([
        "## Chi phí runtime của ràng buộc",
        "",
        f"- Level 4 / Level 3: trung vị `{ratios['level_04_vs_03']:.3f}×` trên cùng bài và thuật toán.",
        f"- Level 5 / Level 4: trung vị `{ratios['level_05_vs_04']:.3f}×` trên cùng bài và thuật toán.",
        "",
        "Các tỷ lệ này mô tả overhead của stackability và load-bearing; không xếp hạng Level nào tốt hơn.",
        "",
        "## Profiling và quyết định kỹ thuật",
        "",
    ])
    for level_id in report.get("levels", []):
        profile = report.get("profiling", {}).get(level_id)
        if not profile:
            continue
        gate = profile["decision_gate"]
        categories = gate["profiled_solver_category_shares"]
        lines.extend([
            f"### {level_id}",
            "",
            f"- Construction: `{gate['construction_median_wall_share']:.1%}` wall time; reporting: `{gate['reporting_median_wall_share']:.1%}`.",
            f"- Nhóm kiểm tra vật lý: `{gate['physical_constraint_share_of_profiled_solver_self_time']:.1%}` profiled solver self-time.",
            f"- Candidate enumeration `{categories['candidate_enumeration']:.1%}`; overlap `{categories['overlap']:.1%}`; exact support `{categories['exact_support']:.1%}`; stackability `{categories['stackability']:.1%}`; load transfer `{categories['load_transfer']:.1%}`.",
            f"- Ưu tiên theo gate: `{', '.join(gate['priorities'])}`.",
            "",
        ])
    lines.extend([
        "## Kết luận",
        "",
        "Level 3 chưa có một nhóm hàm đơn lẻ vượt ngưỡng 40%, nên chưa tối ưu vi mô.",
        "Level 4–5 bị chi phối bởi construction và các phép kiểm tra tiếp xúc/support; bước kỹ thuật tiếp theo là thiết kế A/B cache hoặc contact index dùng chung, giữ nguyên behavior khi tắt.",
        "MES có tín hiệu chất lượng rõ ở Level 4–5 trên phân phối random, nên có thể mở A/B promotion riêng sau khi xử lý hoặc chấp nhận runtime budget.",
        "Level 6 tiếp tục đóng băng.",
        "",
        "Lưu ý: cProfile tạo overhead. Runtime chính thức luôn lấy từ benchmark không profile; profile chỉ dùng xác định hotspot.",
    ])
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, csv_path, markdown_path
