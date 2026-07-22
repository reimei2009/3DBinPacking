"""Deterministic, Level-1-aware interpretation of benchmark summaries.

These functions consume the persisted ``benchmark/summary.csv`` rather than
solver internals, so their conclusions stay reproducible and auditable.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import pandas as pd


COMPARISON_KEYS = ("level", "scenario_id", "input_fingerprint")
_REQUIRED_COLUMNS = {
    "algorithm", "success_rate", "used_containers_mean", "total_cost_mean",
    "algorithm_runtime_mean_seconds",
}


@dataclass(frozen=True)
class BenchmarkAnalysis:
    """Derived, comparable benchmark views and a concise Markdown report."""

    ranking: pd.DataFrame
    pairwise_comparison: pd.DataFrame
    pareto_frontier: pd.DataFrame
    milp_reference_gaps: pd.DataFrame
    report_markdown: str


def _validate_summary(summary: pd.DataFrame) -> pd.DataFrame:
    missing = _REQUIRED_COLUMNS - set(summary.columns)
    if missing:
        raise ValueError(f"Benchmark summary is missing required columns: {', '.join(sorted(missing))}")
    frame = summary.copy()
    for key in COMPARISON_KEYS:
        if key not in frame.columns:
            frame[key] = "legacy" if key == "scenario_id" else "unknown"
    for column in _REQUIRED_COLUMNS - {"algorithm"}:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if "run_count" not in frame:
        frame["run_count"] = 0
    if "optimal_count" not in frame:
        frame["optimal_count"] = 0
    return frame


def build_ranking(summary: pd.DataFrame) -> pd.DataFrame:
    """Rank algorithms within one exact scenario by the Level-1 priority.

    Valid-solution reliability is first; then the Level-1 lexicographic
    objective (containers, cost), followed by mean algorithm runtime.
    """
    frame = _validate_summary(summary)
    frame["has_valid_solution"] = frame["success_rate"] > 0
    frame["ranking_status"] = frame["has_valid_solution"].map({True: "eligible", False: "no_valid_solution"})
    frame["lexicographic_rank"] = pd.NA
    for _, indexes in frame.groupby(list(COMPARISON_KEYS), dropna=False, sort=False).groups.items():
        eligible = frame.loc[indexes][frame.loc[indexes, "has_valid_solution"]].sort_values(
            ["success_rate", "used_containers_mean", "total_cost_mean", "algorithm_runtime_mean_seconds", "algorithm"],
            ascending=[False, True, True, True, True],
            na_position="last",
        )
        frame.loc[eligible.index, "lexicographic_rank"] = range(1, len(eligible) + 1)
    frame["lexicographic_rank"] = frame["lexicographic_rank"].astype("Int64")
    frame["is_lexicographic_winner"] = frame["lexicographic_rank"].eq(1)
    return frame.sort_values([*COMPARISON_KEYS, "lexicographic_rank", "algorithm"], na_position="last").reset_index(drop=True)


def build_pairwise_comparison(ranking: pd.DataFrame) -> pd.DataFrame:
    """Create one neutral row for every unordered algorithm pair per scenario."""
    frame = _validate_summary(ranking)
    records: list[dict[str, object]] = []
    for group_key, group in frame.groupby(list(COMPARISON_KEYS), dropna=False, sort=True):
        rows = group.sort_values("algorithm").to_dict("records")
        for left, right in combinations(rows, 2):
            left_runtime = left["algorithm_runtime_mean_seconds"]
            right_runtime = right["algorithm_runtime_mean_seconds"]
            left_rank, right_rank = left.get("lexicographic_rank"), right.get("lexicographic_rank")
            winner = (
                left["algorithm"] if pd.notna(left_rank) and (pd.isna(right_rank) or left_rank < right_rank)
                else right["algorithm"] if pd.notna(right_rank) and (pd.isna(left_rank) or right_rank < left_rank)
                else ""
            )
            records.append({
                **dict(zip(COMPARISON_KEYS, group_key)),
                "algorithm_a": left["algorithm"], "algorithm_b": right["algorithm"],
                "lexicographic_winner": winner,
                "success_rate_delta_a_minus_b": left["success_rate"] - right["success_rate"],
                "container_delta_a_minus_b": left["used_containers_mean"] - right["used_containers_mean"],
                "cost_delta_a_minus_b": left["total_cost_mean"] - right["total_cost_mean"],
                "runtime_ratio_a_over_b": (left_runtime / right_runtime if pd.notna(left_runtime) and pd.notna(right_runtime) and right_runtime > 0 else None),
            })
    return pd.DataFrame(records)


def build_pareto_frontier(ranking: pd.DataFrame) -> pd.DataFrame:
    """Mark non-dominated valid methods on reliability, quality and runtime."""
    frame = _validate_summary(ranking)
    frame["is_pareto_optimal"] = False
    frame["dominated_by"] = ""
    metrics = ("success_rate", "used_containers_mean", "total_cost_mean", "algorithm_runtime_mean_seconds")
    for _, indexes in frame.groupby(list(COMPARISON_KEYS), dropna=False, sort=False).groups.items():
        eligible = frame.loc[indexes][frame.loc[indexes, "success_rate"] > 0]
        for index, row in eligible.iterrows():
            dominators: list[str] = []
            for other_index, other in eligible.iterrows():
                if other_index == index or any(pd.isna(row[m]) or pd.isna(other[m]) for m in metrics):
                    continue
                no_worse = (
                    other["success_rate"] >= row["success_rate"]
                    and other["used_containers_mean"] <= row["used_containers_mean"]
                    and other["total_cost_mean"] <= row["total_cost_mean"]
                    and other["algorithm_runtime_mean_seconds"] <= row["algorithm_runtime_mean_seconds"]
                )
                strictly_better = (
                    other["success_rate"] > row["success_rate"]
                    or other["used_containers_mean"] < row["used_containers_mean"]
                    or other["total_cost_mean"] < row["total_cost_mean"]
                    or other["algorithm_runtime_mean_seconds"] < row["algorithm_runtime_mean_seconds"]
                )
                if no_worse and strictly_better:
                    dominators.append(str(other["algorithm"]))
            frame.loc[index, "is_pareto_optimal"] = not dominators
            frame.loc[index, "dominated_by"] = ", ".join(sorted(dominators))
    return frame.sort_values([*COMPARISON_KEYS, "is_pareto_optimal", "algorithm"], ascending=[True, True, True, False, True]).reset_index(drop=True)


def build_milp_reference_gaps(ranking: pd.DataFrame) -> pd.DataFrame:
    """Calculate gaps only where an all-optimal MILP row is a valid reference."""
    frame = _validate_summary(ranking)
    records: list[dict[str, object]] = []
    for group_key, group in frame.groupby(list(COMPARISON_KEYS), dropna=False, sort=True):
        milp = group[(group["algorithm"] == "milp_big_m") & (group["success_rate"] == 1) & (group["optimal_count"] == group["run_count"])]
        reference = milp.iloc[0] if len(milp) else None
        for _, row in group.iterrows():
            record: dict[str, object] = {**dict(zip(COMPARISON_KEYS, group_key)), "algorithm": row["algorithm"]}
            if reference is None:
                record.update({"milp_reference_status": "not_available", "container_gap_to_milp": None, "cost_gap_to_milp": None, "runtime_speedup_vs_milp": None})
            else:
                runtime = row["algorithm_runtime_mean_seconds"]
                record.update({
                    "milp_reference_status": "optimal_reference",
                    "container_gap_to_milp": row["used_containers_mean"] - reference["used_containers_mean"],
                    "cost_gap_to_milp": row["total_cost_mean"] - reference["total_cost_mean"],
                    "runtime_speedup_vs_milp": (reference["algorithm_runtime_mean_seconds"] / runtime if pd.notna(runtime) and runtime > 0 else None),
                })
            records.append(record)
    return pd.DataFrame(records)


def render_benchmark_report(ranking: pd.DataFrame, pareto: pd.DataFrame, gaps: pd.DataFrame) -> str:
    winners = ranking[ranking.get("is_lexicographic_winner", False)]
    lines = ["# Benchmark analysis", "", "## Ranking rule", "", "1. Higher valid-solution rate.", "2. Fewer containers.", "3. Lower container cost when the container count ties.", "4. Lower mean algorithm runtime.", "", "## Scenario winners", "", "| Scenario | Winner | Containers | Cost | Runtime (s) |", "| --- | --- | ---: | ---: | ---: |"]
    for row in winners.itertuples(index=False):
        lines.append(f"| {row.scenario_id} | {row.algorithm} | {row.used_containers_mean:g} | {row.total_cost_mean:g} | {row.algorithm_runtime_mean_seconds:.6f} |")
    pareto_count = int(pareto.get("is_pareto_optimal", pd.Series(dtype=bool)).sum())
    reference_count = int((gaps.get("milp_reference_status", pd.Series(dtype=str)) == "optimal_reference").sum())
    lines.extend(["", f"Pareto-optimal rows: {pareto_count}.", f"Rows with an optimal MILP reference: {reference_count}.", "", "Pareto is a trade-off view; it does not replace the Level-1 lexicographic ranking."])
    return "\n".join(lines) + "\n"


def analyze_benchmark(summary: pd.DataFrame) -> BenchmarkAnalysis:
    ranking = build_ranking(summary)
    pareto = build_pareto_frontier(ranking)
    gaps = build_milp_reference_gaps(ranking)
    pairwise = build_pairwise_comparison(ranking)
    return BenchmarkAnalysis(ranking, pairwise, pareto, gaps, render_benchmark_report(ranking, pareto, gaps))
