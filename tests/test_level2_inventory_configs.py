"""Contract tests for Level 2 inventory experiment assets."""

from __future__ import annotations

from container_packing.benchmarks.suites import load_benchmark_suite
from container_packing.benchmarks.corpus import load_benchmark_corpus
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


def test_level2_inventory_scale_suite_covers_20_to_300_items(root) -> None:
    suite = load_benchmark_suite(
        root / "config/level_02/benchmarks/inventory_scale_20_300_manual.yaml"
    )

    assert suite.level_id == "level_02"
    assert suite.repeats == 2
    assert suite.algorithms == (
        "extreme_point_best_fit", "extreme_point_ffd",
    )
    assert [value.item_count for value in suite.scenarios] == [20, 100, 300]
    assert {value.container_count for value in suite.scenarios} == {1}
    assert {value.item_selection_strategy for value in suite.scenarios} == {"prefix"}


def test_large_solver_research_config_and_web_gate_suite_are_bounded(root) -> None:
    config = load_config(
        root / "config/level_02/experiments/inventory_items_20000_fleet_5000.yaml"
    )
    suite = load_benchmark_suite(
        root /
        "config/level_02/benchmarks/solver_research_i20000_f5000_web_gate_manual.yaml"
    )
    assert config["dataset_policy"]["expected_usage_class"] == "solver_research"
    assert config["container_search"]["max_used_container_count"] == 5000
    assert config["container_search"]["time_limit_seconds"] == 180
    assert config["container_search"]["consolidation"]["enabled"] is False
    assert suite.algorithms == ("extreme_point_best_fit",)
    assert suite.repeats == 2
    assert [scenario.item_count for scenario in suite.scenarios] == [
        1000, 5000, 10000, 12389,
    ]


def test_capacity_aware_consolidation_ab_suite_is_bounded_and_comparable(root) -> None:
    suite = load_benchmark_suite(
        root / "config/level_02/benchmarks/capacity_aware_consolidation_ab_manual.yaml"
    )
    config = load_config(
        root /
        "config/level_02/experiments/capacity_aware_consolidation_120s_local.yaml"
    )

    assert suite.level_id == "level_02"
    assert suite.algorithms == ("extreme_point_best_fit", "extreme_point_ffd")
    assert suite.repeats == 2
    assert [value.item_count for value in suite.scenarios] == [
        100, 100, 300, 300, 500, 500,
    ]
    assert {value.container_count for value in suite.scenarios} == {1}
    assert {value.item_selection_strategy for value in suite.scenarios} == {
        "prefix", "stable_random",
    }
    assert config["container_search"]["max_used_container_count"] == 50
    assert config["container_search"]["time_limit_seconds"] == 120
    consolidation = config["container_search"]["consolidation"]
    assert consolidation["time_limit_seconds"] == 100
    assert consolidation["improvement_phase_time_fractions"] == [0.60, 0.40]
    assert consolidation["container_elimination"][
        "adaptive_cluster_elimination"
    ]["maximum_destination_containers"] == 3


def test_level2_mpv_acceptance_suite_is_bounded_and_fixed_orientation(root) -> None:
    suite = load_benchmark_corpus(
        root / "config/level_02/benchmarks/mpv_fixed_orientation_acceptance_manual.yaml"
    )
    config = load_config(
        root / "config/level_02/experiments/mpv_fixed_orientation_acceptance.yaml"
    )

    assert suite.level_id == "level_02"
    assert suite.repeats == 2
    assert {algorithm for case in suite.cases for algorithm in case.algorithms} == {
        "extreme_point_best_fit", "extreme_point_ffd",
    }
    assert len(suite.cases) == 27
    assert {value.item_count for value in suite.cases} == {20, 50, 100}
    assert {value.group for value in suite.cases} == {
        f"mpv_class_{index:02d}" for index in range(1, 10)
    }
    assert all(value.config_overrides for value in suite.cases)
    assert all(
        value.config_overrides["container_search"]["max_used_container_count"]
        == value.container_count
        for value in suite.cases
    )
    assert config["model"]["allow_rotation"] is False
    assert config["model"]["enforce_support"] is True
    assert config["paths"]["processed_dir"].startswith("data/processed/level_02/")


def test_level2_mpv_smoke_suite_has_three_classes_and_six_executions(root) -> None:
    suite = load_benchmark_corpus(
        root / "config/level_02/benchmarks/mpv_fixed_orientation_smoke_manual.yaml"
    )

    assert suite.repeats == 1
    assert len(suite.cases) == 3
    assert {value.case_id for value in suite.cases} == {
        "mpv_c01_n020_i01", "mpv_c05_n020_i01", "mpv_c09_n020_i01",
    }
    assert {
        value.config_overrides["container_search"]["max_used_container_count"]
        for value in suite.cases
    } == {20}
    assert sum(len(value.algorithms) for value in suite.cases) * suite.repeats == 6


def test_mes_inventory_scale_gates_are_bounded_and_ordered(root) -> None:
    expected = {
        100: (10, 60),
        300: (15, 90),
        500: (50, 120),
        1000: (100, 180),
    }
    algorithms = (
        "extreme_point_best_fit", "extreme_point_ffd", "maximal_space_best_fit",
    )
    for item_count, (maximum_containers, deadline) in expected.items():
        config = load_config(
            root /
            f"config/level_02/experiments/mes_inventory_gate_{item_count}_local.yaml"
        )
        suite = load_benchmark_suite(
            root /
            f"config/level_02/benchmarks/mes_inventory_gate_{item_count}_manual.yaml"
        )

        assert config["container_search"]["enabled"] is True
        assert config["container_search"]["max_used_container_count"] == maximum_containers
        assert config["container_search"]["time_limit_seconds"] == deadline
        assert config["container_search"]["secondary_search_score"]["enabled"] is False
        assert config["container_search"]["consolidation"]["enabled"] is False
        assert suite.algorithms == algorithms
        assert suite.repeats == 2
        assert {value.item_count for value in suite.scenarios} == {item_count}
        assert {value.item_selection_strategy for value in suite.scenarios} == {
            "prefix", "stable_random",
        }


def test_mes_secondary_and_repair_suites_have_a_shared_control(root) -> None:
    control = load_benchmark_suite(
        root / "config/level_02/benchmarks/mes_inventory_ep_mes_control_manual.yaml"
    )
    secondary = load_benchmark_suite(
        root / "config/level_02/benchmarks/mes_secondary_kpi_manual.yaml"
    )
    repair = load_benchmark_suite(
        root / "config/level_02/benchmarks/mes_inventory_repair_manual.yaml"
    )
    control_config = load_config(root / control.config_path)
    secondary_config = load_config(root / secondary.config_path)
    repair_config = load_config(root / repair.config_path)

    expected_algorithms = ("extreme_point_best_fit", "maximal_space_best_fit")
    assert control.algorithms == secondary.algorithms == repair.algorithms == expected_algorithms
    assert control.repeats == secondary.repeats == repair.repeats == 2
    assert {
        (value.item_count, value.item_selection_strategy, value.item_selection_seed)
        for value in secondary.scenarios
    }.issubset({
        (value.item_count, value.item_selection_strategy, value.item_selection_seed)
        for value in control.scenarios
    })
    assert {
        (value.item_count, value.item_selection_strategy, value.item_selection_seed)
        for value in repair.scenarios
    } == {
        (value.item_count, value.item_selection_strategy, value.item_selection_seed)
        for value in control.scenarios
    }
    for config in (control_config, secondary_config, repair_config):
        assert config["container_search"]["max_used_container_count"] == 50
        assert config["container_search"]["time_limit_seconds"] == 120
    assert control_config["container_search"]["secondary_search_score"]["enabled"] is False
    assert control_config["container_search"]["consolidation"]["enabled"] is False
    assert secondary_config["container_search"]["secondary_search_score"]["enabled"] is True
    assert secondary_config["container_search"]["consolidation"]["enabled"] is False
    assert repair_config["container_search"]["secondary_search_score"]["enabled"] is False
    assert repair_config["container_search"]["consolidation"]["enabled"] is True


def test_mes_secondary_kpi_scale_gates_are_explicit_and_bounded(root) -> None:
    expected = {500: (50, 120), 1000: (100, 180)}
    for item_count, (maximum_containers, deadline) in expected.items():
        suite = load_benchmark_suite(
            root / f"config/level_02/benchmarks/mes_secondary_kpi_gate_{item_count}_manual.yaml"
        )
        config = load_config(root / suite.config_path)

        assert suite.algorithms == (
            "extreme_point_best_fit", "maximal_space_best_fit",
        )
        assert suite.repeats == 2
        assert {value.item_count for value in suite.scenarios} == {item_count}
        assert {value.item_selection_strategy for value in suite.scenarios} == {
            "prefix", "stable_random",
        }
        assert config["container_search"]["max_used_container_count"] == maximum_containers
        assert config["container_search"]["time_limit_seconds"] == deadline
        assert config["container_search"]["secondary_search_score"]["enabled"] is True
        assert config["container_search"]["consolidation"]["enabled"] is False
