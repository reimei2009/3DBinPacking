"""Phân tích phân phối cho benchmark có provenance đồng nhất.

Các hàm ở đây chỉ đọc bảng kết quả đã persist; không can thiệp objective
chính thức hay solver. Mọi so sánh chất lượng đều khóa theo input fingerprint.
"""

from __future__ import annotations

from itertools import combinations
import ast
import json

import pandas as pd


_P95_MINIMUM_SAMPLE_COUNT = 10
_REPAIR_COMPARISON_COLUMNS = [
    "level", "comparison_group", "comparison_input_fingerprint", "item_count",
    "containers_before", "containers_after", "cost_before", "cost_after",
    "runtime_without_repair_p50_seconds", "runtime_with_repair_p50_seconds",
    "repair_runtime_p50_seconds", "repair_termination_reason", "outcome",
    "incumbent_preserved",
]
_CONTACT_INDEX_COMPARISON_COLUMNS = [
    "level", "comparison_group", "comparison_input_fingerprint", "algorithm",
    "item_count", "paired_execution_count", "status_equivalent",
    "objective_equivalent", "placement_signature_equivalent",
    "rejection_counters_equivalent", "construction_disabled_p50_seconds",
    "construction_enabled_p50_seconds", "construction_speedup_ratio",
    "construction_improvement_ratio", "construction_case_regression_ratio",
    "wall_disabled_p50_seconds", "wall_enabled_p50_seconds",
    "wall_speedup_ratio", "construction_disabled_p95_seconds",
    "construction_enabled_p95_seconds", "wall_disabled_p95_seconds",
    "wall_enabled_p95_seconds", "memory_overhead_ratio", "correctness_gate_passed",
    "construction_case_gate_passed", "wall_case_gate_passed",
    "memory_case_gate_passed",
]


def _official_rows(results: pd.DataFrame) -> pd.DataFrame:
    required = {"success", "input_fingerprint", "algorithm"}
    missing = required - set(results.columns)
    if missing:
        raise ValueError(f"Benchmark results are missing: {', '.join(sorted(missing))}")
    frame = results.copy()
    scenario = (
        frame["scenario_id"].fillna("").astype(str).str.strip()
        if "scenario_id" in frame else pd.Series("", index=frame.index)
    )
    case = (
        frame["case_id"].fillna("").astype(str).str.strip()
        if "case_id" in frame else pd.Series("", index=frame.index)
    )
    frame["case_id"] = case.where(case.ne(""), scenario)
    if frame["case_id"].eq("").any():
        raise ValueError("Benchmark results must identify every row with case_id or scenario_id")
    if "scenario_id" not in frame:
        frame["scenario_id"] = frame["case_id"]
    if "benchmark_stratum" not in frame:
        frame["benchmark_stratum"] = "legacy_unspecified"
    failed_with_objective = (~frame["success"].fillna(False)) & (
        frame.get("objective_value", pd.Series(index=frame.index)).notna()
        | frame.get("used_container_count", pd.Series(index=frame.index)).notna()
        | frame.get("total_container_cost", pd.Series(index=frame.index)).notna()
    )
    if bool(failed_with_objective.any()):
        raise ValueError("Distribution analysis rejects failed rows that carry an official objective")
    return frame


def _fingerprint_keys() -> list[str]:
    return ["level", "case_id", "input_fingerprint"]


def _quantile_when_sufficient(values: pd.Series, quantile: float) -> float | None:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if len(numeric) < _P95_MINIMUM_SAMPLE_COUNT:
        return None
    return float(numeric.quantile(quantile))


def build_case_features(results: pd.DataFrame) -> pd.DataFrame:
    """One provenance row per benchmark instance, never per algorithm."""
    frame = _official_rows(results)
    columns = [
        column for column in (
            "level", "suite_id", "case_id", "scenario_id", "scenario_description", "scenario_tags",
            "dataset_family", "scale_bucket", "benchmark_stratum", "expected_outcome", "item_count",
            "container_count", "item_selection_strategy", "item_selection_seed",
            "input_fingerprint", "selected_item_ids_checksum", "aggregate_lower_bound",
        ) if column in frame.columns
    ]
    return frame[columns].drop_duplicates().sort_values(
        [column for column in ("item_count", "case_id", "input_fingerprint") if column in columns]
    ).reset_index(drop=True)


def build_case_algorithm_summary(results: pd.DataFrame) -> pd.DataFrame:
    """Collapse repeats only inside one exact case, fingerprint and algorithm."""
    frame = _official_rows(results)
    valid = frame[frame["success"].fillna(False)].copy()
    if valid.empty:
        return pd.DataFrame()
    identity = ["level", "case_id", "input_fingerprint", "algorithm"]
    metadata = [
        column for column in (
            "dataset_family", "scale_bucket", "benchmark_stratum", "item_count", "item_selection_strategy",
            "item_selection_seed", "aggregate_lower_bound",
        ) if column in valid.columns
    ]
    keys = [*identity, *metadata]
    summary = valid.groupby(keys, dropna=False, sort=True).agg(
        repeat_execution_count=("success", "size"),
        used_container_count=("used_container_count", "median"),
        total_container_cost=("total_container_cost", "median"),
        wall_runtime_p50_seconds=("wall_runtime_seconds", "median"),
        wall_runtime_min_seconds=("wall_runtime_seconds", "min"),
        wall_runtime_max_seconds=("wall_runtime_seconds", "max"),
        peak_memory_max_bytes=("peak_rss_bytes", "max"),
    ).reset_index()
    return summary


def build_case_differences(results: pd.DataFrame) -> pd.DataFrame:
    """Return only cases where valid algorithms have different official tuples."""
    summary = build_case_algorithm_summary(results)
    if summary.empty:
        return summary
    quality_count = summary.groupby(
        ["level", "case_id", "input_fingerprint"], dropna=False,
    ).apply(
        lambda values: values[["used_container_count", "total_container_cost"]]
        .drop_duplicates().shape[0],
        include_groups=False,
    )
    different_keys = quality_count[quality_count > 1].index
    if different_keys.empty:
        return summary.iloc[0:0].copy()
    indexed = summary.set_index(["level", "case_id", "input_fingerprint"])
    return indexed.loc[different_keys].reset_index().sort_values(
        ["item_count", "case_id", "used_container_count", "total_container_cost", "algorithm"],
    ).reset_index(drop=True)


def build_pairwise_outcomes(results: pd.DataFrame) -> pd.DataFrame:
    """WIN/TIE/LOSS per exact shared instance using the official tuple only."""
    frame = _official_rows(results)
    records: list[dict[str, object]] = []
    for key, group in frame.groupby(_fingerprint_keys(), dropna=False, sort=True):
        by_algorithm = []
        for algorithm, values in group.groupby("algorithm", sort=True):
            valid = values[values["success"].fillna(False)]
            if valid.empty:
                by_algorithm.append((algorithm, None))
                continue
            by_algorithm.append((algorithm, (
                float(valid["used_container_count"].min()),
                float(valid.loc[valid["used_container_count"].eq(valid["used_container_count"].min()), "total_container_cost"].min()),
            )))
        metadata = group.iloc[0]
        for (left, left_quality), (right, right_quality) in combinations(by_algorithm, 2):
            if left_quality is None and right_quality is None:
                outcome = "NO_VALID_SOLUTION"
                winner = None
            elif right_quality is None or (left_quality is not None and left_quality < right_quality):
                outcome, winner = "WIN", left
            elif left_quality is None or right_quality < left_quality:
                outcome, winner = "LOSS", right
            else:
                outcome, winner = "TIE", None
            records.append({
                "level": key[0], "case_id": key[1], "scenario_id": key[1],
                "input_fingerprint": key[2],
                "dataset_family": metadata.get("dataset_family", "unspecified"),
                "scale_bucket": metadata.get("scale_bucket", "unspecified"),
                "benchmark_stratum": metadata.get("benchmark_stratum", "legacy_unspecified"),
                "item_count": metadata.get("item_count"),
                "algorithm_a": left, "algorithm_b": right,
                "outcome_for_a": outcome, "winner": winner,
                "quality_a": left_quality, "quality_b": right_quality,
            })
    return pd.DataFrame(records)


def build_distribution_summary(
    results: pd.DataFrame, *, baseline_algorithm: str = "extreme_point_best_fit",
) -> pd.DataFrame:
    """Aggregate reliability, quality gap, runtime and memory by comparable strata."""
    frame = _official_rows(results)
    for column, default in (
        ("dataset_family", "unspecified"),
        ("scale_bucket", "unspecified"),
        ("benchmark_stratum", "legacy_unspecified"),
    ):
        if column not in frame:
            frame[column] = default
    case_summary = build_case_algorithm_summary(frame)
    if not case_summary.empty:
        case_summary["container_gap_to_lower_bound"] = (
            pd.to_numeric(case_summary["used_container_count"], errors="coerce")
            - pd.to_numeric(case_summary.get("aggregate_lower_bound"), errors="coerce")
        )
        case_summary["container_gap_ratio_to_lower_bound"] = (
            case_summary["container_gap_to_lower_bound"]
            / pd.to_numeric(case_summary.get("aggregate_lower_bound"), errors="coerce").where(
                pd.to_numeric(case_summary.get("aggregate_lower_bound"), errors="coerce") > 0
            )
        )
        best = case_summary.groupby(_fingerprint_keys(), dropna=False)["used_container_count"].transform("min")
        case_summary["container_gap_to_best_observed"] = (
            pd.to_numeric(case_summary["used_container_count"], errors="coerce") - best
        )
        baseline = case_summary[case_summary["algorithm"].eq(baseline_algorithm)].copy()
        if not baseline.empty:
            baseline = baseline.sort_values(
                ["used_container_count", "total_container_cost", "wall_runtime_p50_seconds"],
                na_position="last",
            ).drop_duplicates(_fingerprint_keys())
            baseline = baseline[[
                *_fingerprint_keys(), "used_container_count", "total_container_cost",
            ]].rename(columns={
                "used_container_count": "baseline_container_count",
                "total_container_cost": "baseline_container_cost",
            })
            case_summary = case_summary.merge(
                baseline, on=_fingerprint_keys(), how="left", validate="many_to_one",
            )
            case_summary["container_delta_vs_baseline"] = (
                pd.to_numeric(case_summary["used_container_count"], errors="coerce")
                - pd.to_numeric(case_summary["baseline_container_count"], errors="coerce")
            )
            equal_container_count = case_summary["container_delta_vs_baseline"].eq(0)
            case_summary["cost_delta_vs_baseline_same_container_count"] = (
                pd.to_numeric(case_summary["total_container_cost"], errors="coerce")
                - pd.to_numeric(case_summary["baseline_container_cost"], errors="coerce")
            ).where(equal_container_count)
    group_keys = [
        "level", "algorithm", "dataset_family", "benchmark_stratum",
        "scale_bucket", "item_count",
    ]
    base = frame.groupby(group_keys, dropna=False).agg(
        execution_count=("success", "size"),
        valid_rate=("success", "mean"),
        timeout_rate=("status", lambda values: float(values.astype(str).eq("TIME_LIMIT").mean())),
        invalid_rate=("status", lambda values: float(values.astype(str).isin({"INVALID_SOLUTION", "VALIDATION_FAILED"}).mean())),
        runtime_p50_seconds=("wall_runtime_seconds", "median"),
        runtime_min_seconds=("wall_runtime_seconds", "min"),
        runtime_max_seconds=("wall_runtime_seconds", "max"),
        runtime_p95_seconds=(
            "wall_runtime_seconds", lambda values: _quantile_when_sufficient(values, 0.95)
        ),
        peak_memory_max_bytes=("peak_rss_bytes", "max"),
        peak_memory_p95_bytes=(
            "peak_rss_bytes", lambda values: _quantile_when_sufficient(values, 0.95)
        ),
    ).reset_index()
    base["runtime_per_item_p50"] = base["runtime_p50_seconds"] / base["item_count"]
    if case_summary.empty:
        return base
    quality = case_summary.groupby(group_keys, dropna=False).agg(
        used_containers_median=("used_container_count", "median"),
        container_gap_lower_bound_median=("container_gap_to_lower_bound", "median"),
        container_gap_lower_bound_min=("container_gap_to_lower_bound", "min"),
        container_gap_lower_bound_max=("container_gap_to_lower_bound", "max"),
        container_gap_ratio_lower_bound_median=("container_gap_ratio_to_lower_bound", "median"),
        container_gap_ratio_lower_bound_min=("container_gap_ratio_to_lower_bound", "min"),
        container_gap_ratio_lower_bound_max=("container_gap_ratio_to_lower_bound", "max"),
        container_gap_best_observed_median=("container_gap_to_best_observed", "median"),
    ).reset_index()
    if "container_delta_vs_baseline" in case_summary:
        comparison = case_summary.groupby(group_keys, dropna=False).agg(
            container_delta_vs_baseline_median=("container_delta_vs_baseline", "median"),
            cost_delta_vs_baseline_same_container_median=(
                "cost_delta_vs_baseline_same_container_count", "median",
            ),
        ).reset_index()
        quality = quality.merge(comparison, on=group_keys, how="left", validate="one_to_one")
    return base.merge(quality, on=group_keys, how="left", validate="one_to_one")


def build_determinism_evidence(results: pd.DataFrame) -> pd.DataFrame:
    """Kiem tra repeat co giu nguyen objective va placement signature hay khong."""
    frame = _official_rows(results)
    keys = [
        column for column in (
            "level", "case_id", "input_fingerprint", "algorithm", "random_seed",
        ) if column in frame.columns
    ]
    if not keys:
        return pd.DataFrame()
    rows: list[dict[str, object]] = []
    for values, group in frame.groupby(keys, dropna=False, sort=True):
        key_values = values if isinstance(values, tuple) else (values,)
        successful = group[group["success"].fillna(False)]
        objective_signatures = successful[[
            column for column in ("used_container_count", "total_container_cost")
            if column in successful.columns
        ]].drop_duplicates()
        placement_count = (
            successful["placement_signature"].dropna().nunique()
            if "placement_signature" in successful.columns else 0
        )
        record = dict(zip(keys, key_values))
        record.update({
            "repeat_count": int(len(group)),
            "successful_repeat_count": int(len(successful)),
            "distinct_official_objective_count": int(len(objective_signatures)),
            "distinct_placement_signature_count": int(placement_count),
            "deterministic": bool(
                len(successful) == len(group)
                and len(objective_signatures) <= 1
                and placement_count <= 1
            ),
        })
        rows.append(record)
    return pd.DataFrame(rows)


def build_repair_comparison(results: pd.DataFrame) -> pd.DataFrame:
    """Tong hop controlled A/B khi corpus khai bao repair_disabled/repair_enabled."""
    frame = _official_rows(results)
    required = {
        "comparison_group", "benchmark_variant_id", "comparison_input_fingerprint",
    }
    if not required.issubset(frame.columns):
        return pd.DataFrame(columns=_REPAIR_COMPARISON_COLUMNS)
    frame = frame.dropna(subset=list(required)).copy()
    if frame.empty:
        return pd.DataFrame(columns=_REPAIR_COMPARISON_COLUMNS)
    records: list[dict[str, object]] = []
    group_keys = ["level", "comparison_group", "comparison_input_fingerprint"]
    for key, group in frame.groupby(group_keys, dropna=False, sort=True):
        variants = set(group["benchmark_variant_id"].astype(str))
        expected = {"repair_disabled", "repair_enabled"}
        if variants != expected:
            raise ValueError(
                f"Repair comparison {key[1]} must contain exactly {sorted(expected)}"
            )
        values: dict[str, dict[str, object]] = {}
        for variant, variant_rows in group.groupby("benchmark_variant_id", sort=True):
            successful = variant_rows[variant_rows["success"].fillna(False)]
            best = None
            if not successful.empty:
                best = successful.sort_values(
                    ["used_container_count", "total_container_cost", "wall_runtime_seconds"],
                    na_position="last",
                ).iloc[0]
            repair_runtime = (
                pd.to_numeric(
                    variant_rows["container_consolidation_runtime_seconds"],
                    errors="coerce",
                )
                if "container_consolidation_runtime_seconds" in variant_rows
                else pd.Series(dtype=float)
            )
            values[str(variant)] = {
                "valid_rate": float(variant_rows["success"].mean()),
                "containers": None if best is None else float(best["used_container_count"]),
                "cost": None if best is None else float(best["total_container_cost"]),
                "runtime_p50_seconds": float(variant_rows["wall_runtime_seconds"].median()),
                "repair_runtime_p50_seconds": (
                    None if repair_runtime.empty else float(repair_runtime.median())
                ),
                "termination_reason": _first_non_null(
                    variant_rows.get("container_consolidation_termination_reason")
                ),
            }
        before = values["repair_disabled"]
        after = values["repair_enabled"]
        before_quality = _quality(before)
        after_quality = _quality(after)
        if after_quality is None:
            outcome = "NO_VALID_REPAIR_RESULT"
        elif before_quality is None or after_quality < before_quality:
            outcome = "IMPROVED"
        elif after_quality == before_quality:
            outcome = "UNCHANGED"
        else:
            outcome = "REGRESSION"
        records.append({
            "level": key[0],
            "comparison_group": key[1],
            "comparison_input_fingerprint": key[2],
            "item_count": int(group["item_count"].iloc[0]),
            "containers_before": before["containers"],
            "containers_after": after["containers"],
            "cost_before": before["cost"],
            "cost_after": after["cost"],
            "runtime_without_repair_p50_seconds": before["runtime_p50_seconds"],
            "runtime_with_repair_p50_seconds": after["runtime_p50_seconds"],
            "repair_runtime_p50_seconds": after["repair_runtime_p50_seconds"],
            "repair_termination_reason": after["termination_reason"],
            "outcome": outcome,
            "incumbent_preserved": outcome != "REGRESSION",
        })
    return pd.DataFrame(records, columns=_REPAIR_COMPARISON_COLUMNS)


def _phase_seconds(value: object, phase: str) -> float | None:
    if isinstance(value, dict):
        mapping = value
    elif isinstance(value, str) and value.strip():
        try:
            mapping = json.loads(value)
        except json.JSONDecodeError:
            try:
                mapping = ast.literal_eval(value)
            except (SyntaxError, ValueError):
                return None
    else:
        return None
    if not isinstance(mapping, dict) or mapping.get(phase) is None:
        return None
    try:
        return float(mapping[phase])
    except (TypeError, ValueError):
        return None


def build_contact_index_comparison(results: pd.DataFrame) -> pd.DataFrame:
    """Build paired off/on evidence without changing the official objective."""
    frame = _official_rows(results)
    required = {
        "comparison_group", "benchmark_variant_id", "comparison_input_fingerprint",
        "random_seed", "repeat", "status", "placement_signature",
    }
    if not required.issubset(frame.columns):
        return pd.DataFrame(columns=_CONTACT_INDEX_COMPARISON_COLUMNS)
    frame = frame.dropna(subset=[
        "comparison_group", "benchmark_variant_id", "comparison_input_fingerprint",
    ]).copy()
    if frame.empty:
        return pd.DataFrame(columns=_CONTACT_INDEX_COMPARISON_COLUMNS)
    expected = {"contact_index_disabled", "contact_index_enabled"}
    observed = set(frame["benchmark_variant_id"].astype(str))
    if observed != expected:
        return pd.DataFrame(columns=_CONTACT_INDEX_COMPARISON_COLUMNS)
    frame["construction_seconds"] = frame.get(
        "inventory_search_phase_runtime_seconds", pd.Series(index=frame.index),
    ).map(lambda value: _phase_seconds(value, "construction"))
    counters = [
        column for column in (
            "geometry_rejected_candidates", "support_rejected_candidates",
            "stackability_rejected_candidates", "load_bearing_rejected_candidates",
        ) if column in frame.columns
    ]
    pair_keys = [
        "level", "comparison_group", "comparison_input_fingerprint", "algorithm",
        "random_seed", "repeat",
    ]
    pair_records: list[dict[str, object]] = []
    def same(left: object, right: object) -> bool:
        return bool((pd.isna(left) and pd.isna(right)) or left == right)

    for key, group in frame.groupby(pair_keys, dropna=False, sort=True):
        if set(group["benchmark_variant_id"].astype(str)) != expected or len(group) != 2:
            raise ValueError(f"Contact-index comparison pair {key} is incomplete")
        rows = {
            str(row["benchmark_variant_id"]): row for _, row in group.iterrows()
        }
        disabled = rows["contact_index_disabled"]
        enabled = rows["contact_index_enabled"]
        record = dict(zip(pair_keys, key))
        record.update({
            "item_count": int(group["item_count"].iloc[0]),
            "status_equivalent": disabled["status"] == enabled["status"],
            "objective_equivalent": (
                same(disabled.get("used_container_count"), enabled.get("used_container_count"))
                and same(disabled.get("total_container_cost"), enabled.get("total_container_cost"))
            ),
            "placement_signature_equivalent": (
                same(disabled.get("placement_signature"), enabled.get("placement_signature"))
            ),
            "rejection_counters_equivalent": all(
                same(disabled.get(column), enabled.get(column)) for column in counters
            ),
            "construction_disabled": disabled.get("construction_seconds"),
            "construction_enabled": enabled.get("construction_seconds"),
            "wall_disabled": disabled.get("wall_runtime_seconds"),
            "wall_enabled": enabled.get("wall_runtime_seconds"),
            "memory_disabled": disabled.get("peak_rss_bytes"),
            "memory_enabled": enabled.get("peak_rss_bytes"),
        })
        pair_records.append(record)
    pairs = pd.DataFrame(pair_records)
    records: list[dict[str, object]] = []
    summary_keys = [
        "level", "comparison_group", "comparison_input_fingerprint", "algorithm",
    ]
    for key, group in pairs.groupby(summary_keys, dropna=False, sort=True):
        def median(column: str) -> float | None:
            values = pd.to_numeric(group[column], errors="coerce").dropna()
            return None if values.empty else float(values.median())

        def p95(column: str) -> float | None:
            values = pd.to_numeric(group[column], errors="coerce").dropna()
            return None if values.empty else float(values.quantile(0.95))

        construction_off = median("construction_disabled")
        construction_on = median("construction_enabled")
        wall_off = median("wall_disabled")
        wall_on = median("wall_enabled")
        memory_off = median("memory_disabled")
        memory_on = median("memory_enabled")
        correctness = all(
            bool(group[column].all()) for column in (
                "status_equivalent", "objective_equivalent",
                "placement_signature_equivalent", "rejection_counters_equivalent",
            )
        )
        construction_improvement = (
            None if not construction_off or construction_on is None
            else 1.0 - construction_on / construction_off
        )
        construction_regression = (
            None if not construction_off or construction_on is None
            else max(0.0, construction_on / construction_off - 1.0)
        )
        memory_overhead = (
            None if not memory_off or memory_on is None
            else memory_on / memory_off - 1.0
        )
        records.append({
            "level": key[0], "comparison_group": key[1],
            "comparison_input_fingerprint": key[2], "algorithm": key[3],
            "item_count": int(group["item_count"].iloc[0]),
            "paired_execution_count": len(group),
            "status_equivalent": bool(group["status_equivalent"].all()),
            "objective_equivalent": bool(group["objective_equivalent"].all()),
            "placement_signature_equivalent": bool(
                group["placement_signature_equivalent"].all()
            ),
            "rejection_counters_equivalent": bool(
                group["rejection_counters_equivalent"].all()
            ),
            "construction_disabled_p50_seconds": construction_off,
            "construction_enabled_p50_seconds": construction_on,
            "construction_speedup_ratio": (
                None if not construction_on or construction_off is None
                else construction_off / construction_on
            ),
            "construction_improvement_ratio": construction_improvement,
            "construction_case_regression_ratio": construction_regression,
            "wall_disabled_p50_seconds": wall_off,
            "wall_enabled_p50_seconds": wall_on,
            "wall_speedup_ratio": (
                None if not wall_on or wall_off is None else wall_off / wall_on
            ),
            "construction_disabled_p95_seconds": p95("construction_disabled"),
            "construction_enabled_p95_seconds": p95("construction_enabled"),
            "wall_disabled_p95_seconds": p95("wall_disabled"),
            "wall_enabled_p95_seconds": p95("wall_enabled"),
            "memory_overhead_ratio": memory_overhead,
            "correctness_gate_passed": correctness,
            "construction_case_gate_passed": bool(
                construction_regression is not None and construction_regression <= 0.05
            ),
            "wall_case_gate_passed": bool(
                wall_off is not None and wall_on is not None and wall_on <= wall_off
            ),
            "memory_case_gate_passed": bool(
                memory_overhead is not None and memory_overhead <= 0.20
            ),
        })
    return pd.DataFrame(records, columns=_CONTACT_INDEX_COMPARISON_COLUMNS)


def _quality(values: dict[str, object]) -> tuple[float, float] | None:
    containers = values.get("containers")
    cost = values.get("cost")
    if containers is None or cost is None:
        return None
    return float(containers), float(cost)


def _first_non_null(values: pd.Series | None) -> object | None:
    if values is None:
        return None
    present = values.dropna()
    return None if present.empty else present.iloc[0]
