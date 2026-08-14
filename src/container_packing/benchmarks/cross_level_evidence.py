"""Paired Level 3--5 evidence; never ranks one constraint level above another."""

from __future__ import annotations

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
