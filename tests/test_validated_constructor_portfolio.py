from __future__ import annotations

import json

import pandas as pd
import pytest
import yaml

from container_packing.benchmarks.distribution import (
    build_constructor_portfolio_comparison,
)


@pytest.mark.parametrize("level_id", ["level_04", "level_05"])
def test_portfolio_corpus_materializes_84_cases_and_252_executions(
    root, level_id: str,
) -> None:
    expected = {"random": 60, "stress": 18, "prefix": 6}
    total = 0
    for suffix, case_count in expected.items():
        path = (
            root / f"config/{level_id}/benchmarks/validated_constructor_portfolio_{suffix}_manual.yaml"
        )
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        matrix = raw["matrix"]
        materialized = sum(
            len(selection.get("selection_seeds", [None]))
            for selection in matrix["selections"]
        ) * len(matrix["scales"])
        assert materialized == case_count
        assert raw["repeats"] == 3
        assert matrix["algorithms"] == ["validated_best_fit_mes_portfolio"]
        total += materialized * raw["repeats"]
    assert total == 252


def test_constructor_portfolio_comparison_uses_only_valid_child_objectives() -> None:
    variants = [
        {
            "constructor_id": "extreme_point_best_fit",
            "status": "FEASIBLE",
            "independent_validation_status": "VALID",
            "objective": {"used_container_count": 3, "total_container_cost": 30},
            "runtime_seconds": 2.0,
        },
        {
            "constructor_id": "maximal_space_best_fit",
            "status": "FEASIBLE",
            "independent_validation_status": "VALID",
            "objective": {"used_container_count": 2, "total_container_cost": 20},
            "runtime_seconds": 1.0,
        },
    ]
    results = pd.DataFrame([{
        "level": "level_04",
        "case_id": "case_a",
        "random_seed": 42,
        "repeat": 1,
        "input_fingerprint": "same-input",
        "success": True,
        "used_container_count": 2,
        "total_container_cost": 20,
        "validated_constructor_portfolio_enabled": True,
        "validated_constructor_portfolio_selected": "maximal_space_best_fit",
        "validated_constructor_portfolio_runtime_seconds": 3.2,
        "validated_constructor_portfolio_incumbent_preserved": True,
        "validated_constructor_portfolio_variants_json": json.dumps(variants),
    }])

    comparison = build_constructor_portfolio_comparison(results)

    assert len(comparison) == 1
    row = comparison.iloc[0]
    assert bool(row["selected_matches_best_child"]) is True
    assert row["outcome_vs_best_fit"] == "WIN"
    assert row["runtime_ratio_vs_best_fit"] == pytest.approx(1.6)


def test_constructor_portfolio_comparison_fails_closed_for_invalid_child() -> None:
    variants = [{
        "constructor_id": "extreme_point_best_fit",
        "status": "FEASIBLE",
        "independent_validation_status": "INVALID",
        "objective": {"used_container_count": 1, "total_container_cost": 1},
        "runtime_seconds": 1.0,
    }]
    results = pd.DataFrame([{
        "level": "level_05", "case_id": "case_invalid", "random_seed": 42,
        "repeat": 1, "input_fingerprint": "same", "success": False,
        "used_container_count": None, "total_container_cost": None,
        "validated_constructor_portfolio_enabled": True,
        "validated_constructor_portfolio_selected": None,
        "validated_constructor_portfolio_runtime_seconds": 1.0,
        "validated_constructor_portfolio_incumbent_preserved": False,
        "validated_constructor_portfolio_variants_json": json.dumps(variants),
    }])

    row = build_constructor_portfolio_comparison(results).iloc[0]

    assert pd.isna(row["best_fit_used_container_count"])
    assert row["outcome_vs_best_fit"] == "UNAVAILABLE"
    assert bool(row["selected_matches_best_child"]) is True
