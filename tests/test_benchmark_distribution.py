import pandas as pd
import pytest

from container_packing.benchmarks.distribution import (
    build_case_features,
    build_determinism_evidence,
    build_distribution_summary,
    build_pairwise_outcomes,
    build_repair_comparison,
)


def _rows():
    return pd.DataFrame([
        {
            "level": "level_02", "scenario_id": "case", "input_fingerprint": "same",
            "algorithm": "best", "success": True, "objective_value": 1.0,
            "used_container_count": 2, "total_container_cost": 20.0,
            "item_count": 20, "status": "FEASIBLE", "wall_runtime_seconds": 1.0,
            "peak_rss_bytes": 100, "aggregate_lower_bound": 1,
            "dataset_family": "generated", "scale_bucket": "small",
        },
        {
            "level": "level_02", "scenario_id": "case", "input_fingerprint": "same",
            "algorithm": "ffd", "success": True, "objective_value": 2.0,
            "used_container_count": 3, "total_container_cost": 10.0,
            "item_count": 20, "status": "FEASIBLE", "wall_runtime_seconds": 0.5,
            "peak_rss_bytes": 90, "aggregate_lower_bound": 1,
            "dataset_family": "generated", "scale_bucket": "small",
        },
    ])


def test_distribution_uses_only_shared_fingerprint_and_official_tuple():
    outcomes = build_pairwise_outcomes(_rows())
    assert len(outcomes) == 1
    assert outcomes.iloc[0].outcome_for_a == "WIN"
    assert outcomes.iloc[0].winner == "best"
    assert build_case_features(_rows()).input_fingerprint.tolist() == ["same"]
    summary = build_distribution_summary(_rows(), baseline_algorithm="best")
    assert set(summary.algorithm) == {"best", "ffd"}
    assert set(summary.container_gap_lower_bound_median.dropna()) == {1.0, 2.0}
    by_algorithm = summary.set_index("algorithm")
    assert by_algorithm.loc["ffd", "container_delta_vs_baseline_median"] == 1
    assert pd.isna(
        by_algorithm.loc["ffd", "cost_delta_vs_baseline_same_container_median"]
    )
    assert summary.runtime_p95_seconds.isna().all()
    assert set(summary.runtime_min_seconds) == {0.5, 1.0}
    assert set(summary.runtime_max_seconds) == {0.5, 1.0}


def test_case_id_is_canonical_when_legacy_scenario_id_is_blank():
    first = _rows()
    first["case_id"] = "case-a"
    first["scenario_id"] = ""
    second = _rows()
    second["case_id"] = "case-b"
    second["scenario_id"] = ""
    second["input_fingerprint"] = "other"

    outcomes = build_pairwise_outcomes(pd.concat([first, second], ignore_index=True))

    assert set(outcomes.case_id) == {"case-a", "case-b"}
    assert len(outcomes) == 2


def test_p95_requires_ten_executions_per_algorithm_and_scale():
    frame = pd.concat([_rows().iloc[[0]].copy() for _ in range(10)], ignore_index=True)
    frame["wall_runtime_seconds"] = list(range(1, 11))

    summary = build_distribution_summary(frame)

    assert summary.iloc[0].execution_count == 10
    assert summary.iloc[0].runtime_p50_seconds == pytest.approx(5.5)
    assert summary.iloc[0].runtime_p95_seconds == pytest.approx(9.55)


def test_cross_scale_summary_keeps_item_counts_separate():
    small = _rows()
    large = _rows()
    large["case_id"] = "large"
    large["scenario_id"] = "large"
    large["input_fingerprint"] = "large-input"
    large["item_count"] = 100
    large["used_container_count"] = [8, 9]
    large["aggregate_lower_bound"] = 7

    summary = build_distribution_summary(pd.concat([small, large], ignore_index=True))

    assert set(summary.item_count) == {20, 100}
    assert len(summary) == 4


def test_distribution_rejects_failed_objective_leakage():
    frame = _rows()
    frame.loc[0, "success"] = False
    with pytest.raises(ValueError, match="failed rows"):
        build_distribution_summary(frame)


def test_determinism_evidence_requires_same_objective_and_signature():
    frame = pd.concat([_rows(), _rows()], ignore_index=True)
    frame["random_seed"] = 42
    frame["repeat"] = [1, 1, 2, 2]
    frame["placement_signature"] = ["a", "b", "a", "b"]
    evidence = build_determinism_evidence(frame)
    assert evidence.deterministic.all()
    frame.loc[2, "placement_signature"] = "changed"
    assert not build_determinism_evidence(frame).deterministic.all()


def test_repair_comparison_uses_treatment_fingerprint_and_preserves_incumbent():
    frame = pd.DataFrame([
        {
            "level": "level_02", "scenario_id": "off", "input_fingerprint": "off",
            "comparison_group": "same", "comparison_input_fingerprint": "physical",
            "benchmark_variant_id": "repair_disabled", "algorithm": "best",
            "success": True, "used_container_count": 4, "total_container_cost": 40,
            "wall_runtime_seconds": 1.0, "item_count": 100, "status": "FEASIBLE",
            "objective_value": 1.0, "container_consolidation_runtime_seconds": 0.0,
            "container_consolidation_termination_reason": "disabled",
        },
        {
            "level": "level_02", "scenario_id": "on", "input_fingerprint": "on",
            "comparison_group": "same", "comparison_input_fingerprint": "physical",
            "benchmark_variant_id": "repair_enabled", "algorithm": "best",
            "success": True, "used_container_count": 3, "total_container_cost": 35,
            "wall_runtime_seconds": 3.0, "item_count": 100, "status": "FEASIBLE",
            "objective_value": 2.0, "container_consolidation_runtime_seconds": 2.0,
            "container_consolidation_termination_reason": "valid_consolidated",
        },
    ])
    comparison = build_repair_comparison(frame)
    assert comparison.iloc[0].outcome == "IMPROVED"
    assert comparison.iloc[0].incumbent_preserved
    assert comparison.iloc[0].containers_before == 4
    assert comparison.iloc[0].containers_after == 3
