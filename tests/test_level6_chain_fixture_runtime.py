from __future__ import annotations

from pathlib import Path

from container_packing.levels.level_06_pipeline import run_from_config


def test_registered_level6_runtime_accepts_declared_depth_two_chain(root: Path) -> None:
    result = run_from_config(
        root / "config/level_06/experiments/declared_nesting_chain_fixture.yaml",
        item_count=3,
        container_count=1,
        write_outputs=False,
    )

    assert result.solve.status == "FEASIBLE"
    assert result.validation is not None and result.validation.valid
    assert result.metadata["nesting_relation_count"] == 2
    assert result.metadata["maximum_nesting_depth"] == 2
    assert result.metadata["compound_count"] == 1
    assert result.metadata["nesting_construction_policy"] == "explicit_nesting_best_fit_chain_v1"


def test_registered_best_fit_reuses_depth_two_compound_validation(root: Path) -> None:
    result = run_from_config(
        root / "config/level_06/experiments/declared_nesting_chain_best_fit_fixture.yaml",
        item_count=3,
        container_count=1,
        algorithm_id="extreme_point_best_fit_nesting_fixture",
        write_outputs=False,
    )

    assert result.solve.status == "FEASIBLE"
    assert result.validation is not None and result.validation.valid
    assert result.metadata["fixture_adapter"] == "level_06_nesting_aware_best_fit_compound_v1"
    assert result.metadata["compound_constructor"] == "extreme_point_best_fit_nesting_fixture"
    assert result.metadata["nesting_relation_count"] == 2
    assert result.metadata["compound_count"] == 1
