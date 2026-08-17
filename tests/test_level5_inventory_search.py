"""Nghiệm thu composition inventory-aware cho Level 5."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from container_packing.algorithms.search import exact_support_closures
from container_packing.benchmarks.suites import load_benchmark_suite
from container_packing.data_loader import load_config
from container_packing.experiments.contracts import ExperimentRequest
from container_packing.experiments.runner import run_experiment
from container_packing.levels import level_05_algorithms
from container_packing.levels.level_05_algorithms import execute_level_05
from container_packing.levels.level_05_validation import validate_load_bearing
from container_packing.schemas import Container, Item, Placement


def _item(item_id: str, *, weight: float = 1, maximum: int = 2) -> Item:
    return Item(item_id, 20, 10, 5, weight, source={
        "stackability_code": "1",
        "max_stackability": str(maximum),
    })


def _containers() -> list[Container]:
    return [
        Container("PREFIX_TOO_SMALL", 8, 8, 8, 100, 1, volume_m3=512e-9),
        Container("ROTATED_FIT", 10, 20, 10, 100, 10, volume_m3=2e-6),
        Container("EXPENSIVE", 30, 30, 30, 100, 20, volume_m3=27e-6),
    ]


def _settings(root: Path, *, enabled: bool = True) -> dict:
    return {
        "support": {
            "threshold": 1.0,
            "epsilon_mm": 1e-4,
            "dense_grid_x": 16,
            "dense_grid_y": 16,
        },
        "validation": {
            "coordinate_tolerance_mm": 1e-4,
            "weight_tolerance_kg": 1e-6,
            "load_tolerance_kg": 1e-6,
        },
        "stackability": load_config(
            root / "config/level_04/stackability_rules.yaml"
        ),
        "load_bearing": load_config(
            root / "config/level_05/load_bearing_rules.yaml"
        ),
        "container_search": {
            "enabled": enabled,
            "initial_used_container_count": 1,
            "max_used_container_count": 1,
            "automatically_increase_container_count": False,
            "time_limit_seconds": 5,
            "validation_reserve_seconds": 0.1,
            "consolidation": {"enabled": False},
        },
    }


@pytest.mark.parametrize(
    "algorithm_id",
    ["extreme_point_best_fit", "extreme_point_ffd", "maximal_space_best_fit"],
)
def test_level5_inventory_uses_rotation_and_validates_recursive_load(
    root: Path, algorithm_id: str,
) -> None:
    items = [_item("BOTTOM"), _item("TOP")]
    settings = _settings(root)

    outcome = execute_level_05(algorithm_id, items, _containers(), settings)
    checked = validate_load_bearing(
        items,
        outcome.placements,
        settings["load_bearing"],
        epsilon_mm=1e-4,
        load_tolerance_kg=1e-6,
    )

    assert outcome.solve.status == "FEASIBLE"
    assert checked.result.valid
    assert {value.container_id for value in outcome.placements} == {"ROTATED_FIT"}
    assert {value.orientation_code for value in outcome.placements} == {"YXZ"}
    assert len(checked.edges) == 1
    assert outcome.metadata["inventory_physical_container_count"] == 3


@pytest.mark.parametrize(
    "algorithm_id",
    ["extreme_point_hill_climbing", "extreme_point_simulated_annealing"],
)
def test_level5_inventory_rejects_unsupported_metaheuristics(
    root: Path, algorithm_id: str,
) -> None:
    with pytest.raises(ValueError, match="supports only"):
        execute_level_05(
            algorithm_id, [_item("I1")], _containers(), _settings(root),
        )


def test_level5_inventory_disabled_keeps_existing_metaheuristic_path(
    root: Path,
) -> None:
    settings = _settings(root, enabled=False)
    settings["max_iterations"] = 0

    outcome = execute_level_05(
        "extreme_point_hill_climbing",
        [_item("BOTTOM"), _item("TOP")],
        [_containers()[1]],
        settings,
    )

    assert outcome.solve.status == "FEASIBLE"
    assert "container_inventory_count" not in outcome.metadata
    assert outcome.metadata["initial_constructor"] == "extreme_point_best_fit"


def test_level5_load_invalid_complete_candidate_is_not_accepted(
    root: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        level_05_algorithms,
        "validate_load_bearing",
        lambda *args, **kwargs: SimpleNamespace(
            result=SimpleNamespace(valid=False),
        ),
    )

    outcome = execute_level_05(
        "extreme_point_best_fit", [_item("I1")], _containers(), _settings(root),
    )

    assert outcome.metadata["validated_incumbent_available"] is False
    assert outcome.metadata["validated_incumbent_rejected_invalid"] > 0
    assert outcome.metadata["inventory_construction_termination_reason"] == (
        "bounded_search_space_exhausted"
    )


def test_level5_inventory_rejects_load_above_fragile_item(root: Path) -> None:
    settings = _settings(root)
    settings["load_bearing"] = deepcopy(settings["load_bearing"])
    settings["load_bearing"]["capacity_profile"]["overrides"] = [{
        "item_id": "BOTTOM",
        "is_fragile": True,
        "max_supported_weight_kg": 0,
        "load_capacity_source": "fragile_inventory_fixture",
    }]

    outcome = execute_level_05(
        "extreme_point_best_fit",
        [_item("BOTTOM"), _item("TOP")],
        [_containers()[1]],
        settings,
    )

    assert outcome.solve.status != "FEASIBLE"
    assert outcome.metadata["validated_incumbent_available"] is False
    assert outcome.metadata["validated_incumbent_rejected_invalid"] == 0


def test_level5_load_transfer_chain_is_preserved_by_support_closure() -> None:
    placements = [
        Placement("BOTTOM", "C", 0, 0, 0, 10, 20, 5, 1, "YXZ"),
        Placement("MIDDLE", "C", 0, 0, 5, 10, 20, 5, 1, "YXZ"),
        Placement("TOP", "C", 0, 0, 10, 10, 20, 5, 1, "YXZ"),
    ]

    closures = exact_support_closures(placements, epsilon_mm=1e-4)

    assert closures["BOTTOM"] == frozenset({"BOTTOM", "MIDDLE", "TOP"})
    assert closures["MIDDLE"] == frozenset({"MIDDLE", "TOP"})
    assert closures["TOP"] == frozenset({"TOP"})


def test_level5_inventory_config_is_isolated_and_solver_qualified(
    root: Path,
) -> None:
    config = load_config(
        root / "config/level_05/experiments/inventory_items_1000_fleet_500.yaml"
    )

    assert config["project"]["level_id"] == "level_05"
    assert config["model"]["enforce_load_bearing"] is True
    assert config["model"]["enforce_load_transfer"] is True
    assert config["orientation"]["profile"] == "horizontal_rotatable"
    assert config["container_search"]["enabled"] is True
    assert config["container_search"]["max_used_container_count"] == 30
    assert config["container_search"]["time_limit_seconds"] == 180
    assert config["container_search"]["validation_reserve_seconds"] == 3
    assert config["container_search"]["consolidation"]["enabled"] is False
    assert config["paths"]["processed_dir"].startswith("data/processed/level_05/")
    assert config["dataset_policy"]["expected_usage_class"] == "solver_research"


def test_level5_inventory_pipeline_writes_isolated_valid_load_graph(
    root: Path, tmp_path: Path,
) -> None:
    raw_items = tmp_path / "items.csv"
    raw_items.write_text(
        "id_item,length,width,height,weight,nesting_height,stackability_code,forced_orientation,max_stackability\n"
        "BOTTOM,20,10,5,1,0,1,w,2\n"
        "TOP,20,10,5,1,0,1,w,2\n",
        encoding="utf-8",
    )
    config = load_config(root / "config/level_05/default.yaml")
    config["paths"].update({
        "raw_items_csv": str(raw_items),
        "processed_dir": str(tmp_path / "processed" / "level_05"),
        "manifest_json": str(
            tmp_path / "processed" / "level_05" / "latest_manifest.json"
        ),
        "output_root": str(tmp_path / "outputs"),
    })
    config["containers"] = [{
        "container_id": "ROTATED_FIT",
        "length_mm": 10,
        "width_mm": 20,
        "height_mm": 10,
        "max_weight_kg": 100,
        "cost": 10,
        "availability": 1,
    }]
    config["instance"] = {"item_count": 2, "container_count": 1}
    config["container_search"].update({
        "enabled": True,
        "initial_used_container_count": 1,
        "max_used_container_count": 1,
        "automatically_increase_container_count": False,
        "time_limit_seconds": 5,
        "validation_reserve_seconds": 0.1,
    })
    config["container_search"]["consolidation"]["enabled"] = False
    config["algorithms"]["extreme_point_best_fit"]["contact_support_index"] = {
        "enabled": True,
    }
    config_path = tmp_path / "level_05_inventory.yaml"
    config_path.write_text(
        yaml.safe_dump(config, sort_keys=False), encoding="utf-8",
    )

    result = run_experiment(ExperimentRequest(
        "level_05", "extreme_point_best_fit", config_path, 2, 1,
    ))

    assert result.solve.status == "FEASIBLE"
    assert result.validation is not None and result.validation.valid
    assert result.metadata["contact_support_index_enabled"] is True
    assert result.metadata["contact_support_index_queries"] > 0
    assert {value.orientation_code for value in result.placements} == {"YXZ"}
    run_dir = Path(result.metadata["run_dir"])
    assert run_dir.parts[-4:-2] == ("outputs", "level_05")
    assert (run_dir / "solution" / "load_bearing.csv").is_file()
    assert (run_dir / "solution" / "load_transfer.csv").is_file()
    assert (run_dir / "validation" / "load_bearing_validation.json").is_file()


def test_level5_inventory_promotion_suite_contract(root: Path) -> None:
    suite = load_benchmark_suite(
        root / "config/level_05/benchmarks/inventory_promotion_20_500_manual.yaml"
    )

    assert suite.level_id == "level_05"
    assert suite.repeats == 2
    assert suite.algorithms == (
        "extreme_point_best_fit", "extreme_point_ffd", "maximal_space_best_fit",
    )
    assert [value.item_count for value in suite.scenarios] == [20, 100, 300, 500]
    assert all(value.container_count == 1 for value in suite.scenarios)
    assert len(suite.scenarios) * len(suite.algorithms) * suite.repeats == 24
