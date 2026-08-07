from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from container_packing.algorithms.search import ContainerSearchConfiguration
from container_packing.data_loader import load_config
from container_packing.instance_data import prepare_instance
from container_packing.levels.level_01_algorithms import execute_level_01
from container_packing.levels.level_01_pipeline import run_from_config
from container_packing.schemas import Container, Item


def _inventory_search_config(root: Path, tmp_path: Path) -> tuple[dict, Path]:
    config = load_config(root / "config/level_01/default.yaml")
    config["project"]["algorithm_id"] = "extreme_point_best_fit"
    config["instance"].update({"item_count": 1, "container_count": 1})
    config["container_search"].update({
        "enabled": True,
        "initial_used_container_count": 1,
        "max_used_container_count": 1,
        "automatically_increase_container_count": False,
        "time_limit_seconds": 5,
    })
    config["containers"] = [
        {
            "container_id": "C_PREFIX_TOO_SMALL", "length_mm": 100,
            "width_mm": 100, "height_mm": 100, "max_weight_kg": 5000,
            "cost": 1, "availability": 1,
        },
        {
            "container_id": "C_EXPENSIVE", "length_mm": 2000,
            "width_mm": 2000, "height_mm": 2000, "max_weight_kg": 5000,
            "cost": 20, "availability": 1,
        },
        {
            "container_id": "C_CHEAPEST_FEASIBLE", "length_mm": 1000,
            "width_mm": 1000, "height_mm": 1000, "max_weight_kg": 5000,
            "cost": 10, "availability": 1,
        },
    ]
    config["paths"]["processed_dir"] = str(tmp_path / "processed")
    config["paths"]["manifest_json"] = str(tmp_path / "processed/latest.json")
    config_path = tmp_path / "inventory_search.yaml"
    config_path.write_text(
        yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
    )
    return config, config_path


def test_container_search_configuration_rejects_invalid_values() -> None:
    with pytest.raises(ValueError, match="initial_used_container_count"):
        ContainerSearchConfiguration.from_mapping({
            "enabled": True, "initial_used_container_count": 0,
        })
    with pytest.raises(ValueError, match="soft_volume_buffer_ratio"):
        ContainerSearchConfiguration.from_mapping({
            "enabled": True, "soft_volume_buffer_ratio": 1.1,
        })
    with pytest.raises(ValueError, match="must be true or false"):
        ContainerSearchConfiguration.from_mapping({"enabled": "true"})
    with pytest.raises(ValueError, match="validation_reserve_seconds"):
        ContainerSearchConfiguration.from_mapping({
            "enabled": True,
            "time_limit_seconds": 5,
            "validation_reserve_seconds": 5,
        })
    with pytest.raises(ValueError, match="Legacy container-elimination"):
        ContainerSearchConfiguration.from_mapping({
            "consolidation": {
                "container_elimination": {"maximum_partial_repack_items": 8},
            },
        })
    with pytest.raises(ValueError, match="must not exceed"):
        ContainerSearchConfiguration.from_mapping({
            "validation_reserve_seconds": 1,
            "consolidation": {
                "container_elimination": {
                    "adaptive_cluster_elimination": {
                        "enabled": True,
                        "minimum_validation_reserve_seconds": 2,
                    },
                },
            },
        })

    unlimited = ContainerSearchConfiguration.from_mapping({
        "enabled": True,
        "time_limit_seconds": None,
        "validation_reserve_seconds": 2,
    })
    assert unlimited.time_limit_seconds is None
    assert unlimited.metadata()["container_search_unlimited_time"] is True


def test_prepare_instance_reads_full_catalog_only_when_feature_is_enabled(
    root: Path, tmp_path: Path,
) -> None:
    enabled, _ = _inventory_search_config(root, tmp_path)
    disabled = {
        **enabled,
        "container_search": {**enabled["container_search"], "enabled": False},
        "paths": {
            **enabled["paths"],
            "processed_dir": str(tmp_path / "legacy"),
            "manifest_json": str(tmp_path / "legacy/latest.json"),
        },
    }

    inventory_manifest = prepare_instance(
        root, enabled, item_count=1, container_count=1,
    )
    legacy_manifest = prepare_instance(
        root, disabled, item_count=1, container_count=1,
    )

    assert inventory_manifest["n_containers"] == 3
    assert inventory_manifest["requested_used_container_count"] == 1
    assert inventory_manifest["container_search_enabled"] is True
    assert legacy_manifest["n_containers"] == 1
    assert legacy_manifest["container_search_enabled"] is False


def test_level1_best_fit_selects_the_cheapest_feasible_container_from_catalog(
    root: Path, tmp_path: Path,
) -> None:
    _, config_path = _inventory_search_config(root, tmp_path)

    result = run_from_config(
        config_path,
        item_count=1,
        container_count=1,
        algorithm_id="extreme_point_best_fit",
        write_outputs=False,
    )

    assert result.solve.status == "FEASIBLE"
    assert result.validation is not None and result.validation.valid
    assert {value.container_id for value in result.placements} == {
        "C_CHEAPEST_FEASIBLE"
    }
    assert result.metadata["container_inventory_count"] == 3
    assert result.metadata["requested_used_container_count"] == 1
    assert result.metadata["hard_precheck_valid"] is True
    assert result.metadata["container_count"] == 1


def test_level1_container_search_rejects_maximum_larger_than_inventory(
    root: Path, tmp_path: Path,
) -> None:
    config, config_path = _inventory_search_config(root, tmp_path)
    config["container_search"].update({
        "max_used_container_count": 4,
        "automatically_increase_container_count": True,
    })
    config_path.write_text(
        yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="exceeds the available physical inventory"):
        run_from_config(
            config_path,
            item_count=1,
            container_count=1,
            algorithm_id="extreme_point_best_fit",
            write_outputs=False,
        )


def test_level1_inventory_search_rejects_unsupported_algorithm(
    root: Path, tmp_path: Path,
) -> None:
    _, config_path = _inventory_search_config(root, tmp_path)

    with pytest.raises(ValueError, match="currently supports only"):
        run_from_config(
            config_path,
            item_count=1,
            container_count=1,
            algorithm_id="milp_big_m",
            write_outputs=False,
        )


def test_adaptive_search_increases_cardinality_from_safe_lower_bound() -> None:
    containers = [
        Container("C1", 10, 10, 10, 1, 10, volume_m3=1e-6),
        Container("C2", 10, 10, 10, 1, 10, volume_m3=1e-6),
    ]
    items = [
        Item("I1", 1, 1, 1, 1),
        Item("I2", 1, 1, 1, 1),
    ]

    outcome = execute_level_01(
        "extreme_point_best_fit",
        items,
        containers,
        {
            "subset_enumeration_limit": 10,
            "container_search": {
                "enabled": True,
                "initial_used_container_count": 1,
                "max_used_container_count": 2,
                "automatically_increase_container_count": True,
            },
        },
    )

    assert outcome.solve.status == "FEASIBLE"
    assert {value.container_id for value in outcome.placements} == {"C1", "C2"}
    assert outcome.metadata["container_subset_cardinalities_considered"] == [2]


def test_strict_count_below_lower_bound_returns_actionable_diagnostics() -> None:
    containers = [
        Container("C1", 10, 10, 10, 1, 10, volume_m3=1e-6),
        Container("C2", 10, 10, 10, 1, 10, volume_m3=1e-6),
    ]
    items = [Item("I1", 1, 1, 1, 1), Item("I2", 1, 1, 1, 1)]

    outcome = execute_level_01(
        "extreme_point_ffd",
        items,
        containers,
        {
            "subset_enumeration_limit": 10,
            "container_search": {
                "enabled": True,
                "initial_used_container_count": 1,
                "max_used_container_count": 2,
                "automatically_increase_container_count": False,
            },
        },
    )

    assert outcome.solve.status == "INFEASIBLE_HEURISTIC"
    assert outcome.solve.objective_value is None
    assert outcome.metadata["construction_termination_reason"] == (
        "container_count_limit_below_aggregate_lower_bound"
    )
    assert outcome.metadata["unpacked_item_count"] == 2
