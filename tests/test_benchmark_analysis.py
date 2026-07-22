import pandas as pd
import pytest

from container_packing.benchmarks.analysis import analyze_benchmark


def _summary() -> pd.DataFrame:
    common = {"level": "level_01", "scenario_id": "small", "input_fingerprint": "same", "run_count": 1, "optimal_count": 0}
    return pd.DataFrame([
        {**common, "algorithm": "milp_big_m", "success_rate": 1.0, "used_containers_mean": 2, "total_cost_mean": 100, "algorithm_runtime_mean_seconds": 5.0, "optimal_count": 1},
        {**common, "algorithm": "extreme_point_ffd", "success_rate": 1.0, "used_containers_mean": 2, "total_cost_mean": 100, "algorithm_runtime_mean_seconds": 0.1},
        {**common, "algorithm": "extreme_point_best_fit", "success_rate": 1.0, "used_containers_mean": 3, "total_cost_mean": 110, "algorithm_runtime_mean_seconds": 6.0},
        {**common, "algorithm": "failed", "success_rate": 0.0, "used_containers_mean": None, "total_cost_mean": None, "algorithm_runtime_mean_seconds": 0.01},
    ])


def test_analysis_applies_level_one_ranking_and_milp_reference_gap():
    analysis = analyze_benchmark(_summary())
    ranking = analysis.ranking.set_index("algorithm")
    assert ranking.loc["extreme_point_ffd", "lexicographic_rank"] == 1
    assert ranking.loc["milp_big_m", "lexicographic_rank"] == 2
    assert pd.isna(ranking.loc["failed", "lexicographic_rank"])

    gaps = analysis.milp_reference_gaps.set_index("algorithm")
    assert gaps.loc["extreme_point_ffd", "milp_reference_status"] == "optimal_reference"
    assert gaps.loc["extreme_point_ffd", "container_gap_to_milp"] == 0
    assert gaps.loc["extreme_point_best_fit", "container_gap_to_milp"] == 1
    assert gaps.loc["extreme_point_ffd", "runtime_speedup_vs_milp"] == pytest.approx(50.0)


def test_analysis_marks_pareto_and_produces_pairwise_rows():
    analysis = analyze_benchmark(_summary())
    pareto = analysis.pareto_frontier.set_index("algorithm")
    assert bool(pareto.loc["extreme_point_ffd", "is_pareto_optimal"])
    assert not bool(pareto.loc["extreme_point_best_fit", "is_pareto_optimal"])
    assert "extreme_point_ffd" in pareto.loc["extreme_point_best_fit", "dominated_by"]
    assert len(analysis.pairwise_comparison) == 6
    assert "Scenario winners" in analysis.report_markdown


def test_milp_gap_is_not_claimed_when_milp_is_not_proven_optimal():
    frame = _summary()
    frame.loc[frame.algorithm == "milp_big_m", "optimal_count"] = 0
    gaps = analyze_benchmark(frame).milp_reference_gaps
    assert set(gaps["milp_reference_status"]) == {"not_available"}
