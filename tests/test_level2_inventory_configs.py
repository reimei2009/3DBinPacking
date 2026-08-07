"""Contract tests for Level 2 inventory experiment assets."""

from __future__ import annotations

from container_packing.benchmarks.suites import load_benchmark_suite
from container_packing.data_loader import load_config


def test_level2_inventory_experiments_keep_processed_data_isolated(root) -> None:
    for fleet, physical_count in (("500", 500), ("5000", 5000)):
        config = load_config(root / f"config/level_02/experiments/inventory_fleet_{fleet}.yaml")

        assert config["project"]["level_id"] == "level_02"
        assert config["container_search"]["enabled"] is True
        assert config["paths"]["processed_dir"].startswith("data/processed/level_02/")
        assert config["paths"]["manifest_json"].startswith("data/processed/level_02/")
        assert config["dataset_policy"]["expected_usage_class"] == "solver_research"
        assert f"fleet_{fleet}" in config["paths"]["raw_containers_csv"]
        assert physical_count > 0

    research = load_config(
        root / "config/level_02/experiments/inventory_items_1000_fleet_500.yaml"
    )
    assert "level_02_inventory_items_1000_fleet_500_t10_v1" in (
        research["paths"]["raw_items_csv"]
    )
    assert research["container_search"]["consolidation"]["enabled"] is True

    scale_500 = load_config(
        root /
        "config/level_02/experiments/"
        "inventory_items_1000_fleet_500_scale_500_acceptance.yaml"
    )
    assert scale_500["instance"]["item_count"] == 500
    assert scale_500["container_search"]["max_used_container_count"] == 20
    assert scale_500["container_search"]["consolidation"][
        "container_elimination"
    ]["enabled"] is True


def test_level2_inventory_benchmark_gates_have_bounded_repeats_and_supported_algorithms(root) -> None:
    for fleet, expected_items in (("500", {20, 50}), ("5000", {100})):
        suite = load_benchmark_suite(
            root / f"config/level_02/benchmarks/inventory_fleet_{fleet}_manual.yaml"
        )

        assert suite.level_id == "level_02"
        assert suite.algorithms == ("extreme_point_best_fit", "extreme_point_ffd")
        assert suite.repeats == 2
        assert {scenario.item_count for scenario in suite.scenarios} == expected_items
