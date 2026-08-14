"""Nghiệm thu composition inventory-aware cho Level 3."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from container_packing.algorithms.orientation import (
    fixed_orientation_provider,
    horizontal_orientation_provider,
)
from container_packing.algorithms.search import (
    normalize_container_inventory,
    run_hard_precheck,
)
from container_packing.benchmarks.suites import load_benchmark_suite
from container_packing.data_loader import load_config
from container_packing.experiments.contracts import ExperimentRequest
from container_packing.experiments.runner import run_experiment
from container_packing.levels.level_03_algorithms import execute_level_03
from container_packing.levels.level_03_validation import validate_solution
from container_packing.schemas import Container, Item
from container_packing.algorithms.search.inventory_consolidation import (
    rank_destination_compatibility,
)


def _containers() -> list[Container]:
    return [
        Container("PREFIX_TOO_SMALL", 8, 8, 8, 100, 1, volume_m3=512e-9),
        Container("ROTATED_FIT", 10, 20, 10, 100, 10, volume_m3=2e-6),
        Container("EXPENSIVE", 30, 30, 30, 100, 20, volume_m3=27e-6),
    ]


def _settings(*, enabled: bool = True) -> dict:
    return {
        "support": {
            "threshold": 0.8,
            "epsilon_mm": 1e-4,
            "dense_grid_x": 16,
            "dense_grid_y": 16,
        },
        "validation": {
            "coordinate_tolerance_mm": 1e-4,
            "weight_tolerance_kg": 1e-6,
        },
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


def test_horizontal_orientation_is_used_by_inventory_hard_precheck() -> None:
    item = Item("ROTATE_ME", 20, 10, 10, 1)
    inventory = normalize_container_inventory([_containers()[1]])

    fixed = run_hard_precheck(
        [item], inventory, orientation_provider=fixed_orientation_provider(),
    )
    horizontal = run_hard_precheck(
        [item], inventory, orientation_provider=horizontal_orientation_provider(),
    )

    assert not fixed.valid
    assert {issue.code for issue in fixed.issues} == {"ITEM_TOO_LARGE"}
    assert horizontal.valid


def test_horizontal_orientation_guides_partial_repack_destination_ranking() -> None:
    item = Item("ROTATE_ME", 20, 10, 10, 1)
    container = _containers()[1]

    fixed = rank_destination_compatibility(
        target_placements=[],
        all_placements=[],
        containers=(container,),
        item_by_id={item.item_id: item},
        failed_item_id=item.item_id,
        orientation_provider=fixed_orientation_provider(),
    )
    horizontal = rank_destination_compatibility(
        target_placements=[],
        all_placements=[],
        containers=(container,),
        item_by_id={item.item_id: item},
        failed_item_id=item.item_id,
        orientation_provider=horizontal_orientation_provider(),
    )

    assert fixed[0].extreme_point_compatible_count == 0
    assert horizontal[0].extreme_point_compatible_count > 0


@pytest.mark.parametrize(
    "algorithm_id",
    ["extreme_point_best_fit", "extreme_point_ffd", "maximal_space_best_fit"],
)
def test_level3_inventory_uses_full_catalog_and_rotates_item(algorithm_id: str) -> None:
    item = Item("ROTATE_ME", 20, 10, 10, 1)

    outcome = execute_level_03(algorithm_id, [item], _containers(), _settings())

    assert outcome.solve.status == "FEASIBLE"
    assert {value.container_id for value in outcome.placements} == {"ROTATED_FIT"}
    assert [value.orientation_code for value in outcome.placements] == ["YXZ"]
    checked = validate_solution([item], _containers(), outcome.placements)
    assert checked.result.valid
    assert outcome.metadata["hard_precheck_valid"] is True
    assert outcome.metadata["orientation_provider"] == "horizontal_orientation_provider"


@pytest.mark.parametrize(
    "algorithm_id",
    ["milp_big_m", "extreme_point_hill_climbing", "extreme_point_simulated_annealing"],
)
def test_level3_inventory_rejects_unsupported_algorithms(algorithm_id: str) -> None:
    with pytest.raises(ValueError, match="supports only"):
        execute_level_03(
            algorithm_id,
            [Item("I1", 1, 1, 1, 1)],
            _containers(),
            _settings(),
        )


def test_level3_inventory_config_is_level_isolated_and_solver_qualified(root: Path) -> None:
    config = load_config(
        root / "config/level_03/experiments/inventory_items_1000_fleet_500.yaml"
    )

    assert config["project"]["level_id"] == "level_03"
    assert config["model"]["allow_rotation"] is True
    assert config["orientation"]["profile"] == "horizontal_rotatable"
    assert config["container_search"]["enabled"] is True
    assert config["container_search"]["max_used_container_count"] == 23
    assert config["paths"]["processed_dir"].startswith("data/processed/level_03/")
    assert config["dataset_policy"]["expected_usage_class"] == "solver_research"


def test_level3_inventory_pipeline_writes_isolated_valid_rotated_run(
    root: Path, tmp_path: Path,
) -> None:
    raw_items = tmp_path / "items.csv"
    raw_items.write_text(
        "id_item,length,width,height,weight,nesting_height,stackability_code,forced_orientation,max_stackability\n"
        "ROTATE_ME,20,10,10,1,0,0,w,1\n",
        encoding="utf-8",
    )
    config = load_config(root / "config/level_03/default.yaml")
    config["paths"].update({
        "raw_items_csv": str(raw_items),
        "processed_dir": str(tmp_path / "processed" / "level_03"),
        "manifest_json": str(tmp_path / "processed" / "level_03" / "latest_manifest.json"),
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
    config["instance"] = {"item_count": 1, "container_count": 1}
    config["container_search"].update({
        "enabled": True,
        "initial_used_container_count": 1,
        "max_used_container_count": 1,
        "automatically_increase_container_count": False,
        "time_limit_seconds": 5,
        "validation_reserve_seconds": 0.1,
    })
    config["container_search"]["consolidation"]["enabled"] = False
    config_path = tmp_path / "level_03_inventory.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    result = run_experiment(ExperimentRequest(
        "level_03", "extreme_point_best_fit", config_path, 1, 1,
    ))

    assert result.solve.status == "FEASIBLE"
    assert result.validation is not None and result.validation.valid
    assert [value.orientation_code for value in result.placements] == ["YXZ"]
    run_dir = Path(result.metadata["run_dir"])
    assert run_dir.parts[-4:-2] == ("outputs", "level_03")


def test_level3_inventory_promotion_suite_contract(root: Path) -> None:
    suite = load_benchmark_suite(
        root / "config/level_03/benchmarks/inventory_promotion_20_500_manual.yaml"
    )

    assert suite.level_id == "level_03"
    assert suite.repeats == 2
    assert suite.algorithms == (
        "extreme_point_best_fit", "extreme_point_ffd", "maximal_space_best_fit",
    )
    assert [value.item_count for value in suite.scenarios] == [20, 100, 300, 500]
    assert all(value.container_count == 1 for value in suite.scenarios)
    assert len(suite.scenarios) * len(suite.algorithms) * suite.repeats == 24
