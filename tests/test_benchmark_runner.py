import json
from pathlib import Path

import pandas as pd
import yaml
import pytest

from container_packing.benchmarks import run_benchmark
from container_packing.benchmarks.runner import _aggregate
from container_packing.benchmarks.suites import BenchmarkScenario, load_benchmark_suite
from container_packing.data_loader import load_config


def test_benchmark_creates_isolated_aggregate_and_source_runs(root: Path, tmp_path: Path):
    config = load_config(root / "config/level_01/default.yaml")
    config["paths"]["raw_items_csv"] = str(root / "data/raw/dataset_small_items_original.csv")
    config["paths"]["processed_dir"] = str(tmp_path / "processed/level_01")
    config["paths"]["manifest_json"] = str(tmp_path / "processed/level_01/latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / "outputs")
    config_path = tmp_path / "level_01.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    result = run_benchmark(
        level_id="level_01", algorithm_ids=[
            "milp_big_m", "extreme_point_best_fit", "extreme_point_ffd", "extreme_point_hill_climbing",
            "extreme_point_simulated_annealing", "maximal_space_best_fit",
        ], item_counts=[1],
        container_counts=[2], repeats=1, config_path=config_path, project_root=root,
    )

    assert result.successful
    assert "__level_01__benchmark__" in result.benchmark_id
    assert result.run_dir.parent.name == "runs"
    assert (result.run_dir / "benchmark/results.csv").is_file()
    assert (result.run_dir / "benchmark/summary.csv").is_file()
    assert (result.run_dir / "benchmark/ranking.csv").is_file()
    assert (result.run_dir / "benchmark/pairwise_comparison.csv").is_file()
    assert (result.run_dir / "benchmark/pareto_frontier.csv").is_file()
    assert (result.run_dir / "benchmark/milp_reference_gaps.csv").is_file()
    assert (result.run_dir / "logs/run.log").is_file()
    manifest = json.loads((result.run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_type"] == "benchmark"
    assert manifest["case_count"] == 6
    assert manifest["successful_case_count"] == 6
    assert len(manifest["source_runs"]) == 6
    assert len(set(result.results["experiment_run_id"])) == 6
    assert set(result.summary["algorithm"]) == {
        "milp_big_m", "extreme_point_best_fit", "extreme_point_ffd", "extreme_point_hill_climbing",
        "extreme_point_simulated_annealing", "maximal_space_best_fit",
    }
    assert set(result.summary["run_count"]) == {1}
    assert set(result.summary["seed_count"]) == {1}
    assert set(result.results["random_seed"]) == {42}
    assert manifest["random_seeds"] == [42]
    assert result.analysis.ranking["is_lexicographic_winner"].sum() == 1


def test_multi_seed_sweep_tracks_seed_repeats_and_resolved_configs(root: Path, tmp_path: Path):
    config = load_config(root / "config/level_01/default.yaml")
    config["paths"]["raw_items_csv"] = str(root / "data/raw/dataset_small_items_original.csv")
    config["paths"]["processed_dir"] = str(tmp_path / "processed/level_01")
    config["paths"]["manifest_json"] = str(tmp_path / "processed/level_01/latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / "outputs")
    config_path = tmp_path / "level_01.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    result = run_benchmark(
        level_id="level_01", algorithm_ids=["extreme_point_simulated_annealing"],
        item_counts=[10], container_counts=[3], seeds=[7, 11, 19], repeats=2,
        config_path=config_path, project_root=root,
    )

    assert result.successful
    assert "__seeds3_" in result.benchmark_id
    assert len(result.results) == 6
    assert set(result.results["random_seed"]) == {7, 11, 19}
    assert set(result.results["repeat"]) == {1, 2}
    assert result.summary.iloc[0].run_count == 6
    assert result.summary.iloc[0].seed_count == 3
    assert result.summary.iloc[0].repeats_per_seed == 2
    assert 1 <= result.summary.iloc[0].distinct_solution_count <= 3
    assert result.results.groupby("random_seed")["placement_signature"].nunique().eq(1).all()

    manifest = json.loads((result.run_dir / "manifest.json").read_text(encoding="utf-8"))
    request = json.loads((result.run_dir / "benchmark/request.json").read_text(encoding="utf-8"))
    assert manifest["random_seed"] is None
    assert manifest["random_seeds"] == [7, 11, 19]
    assert manifest["repeats_per_seed"] == 2
    assert request["random_seeds"] == [7, 11, 19]
    for row in result.results.itertuples():
        run_config = yaml.safe_load((Path(row.experiment_run_dir) / "resolved_config.yaml").read_text(encoding="utf-8"))
        assert run_config["project"]["random_seed"] == row.random_seed
        assert f"__seed{row.random_seed}" in row.experiment_run_id


@pytest.mark.parametrize("seeds", [[], [-1], [7, 7]])
def test_rejects_invalid_seed_sweeps(root: Path, tmp_path: Path, seeds):
    with pytest.raises(ValueError, match="seeds"):
        run_benchmark(
            level_id="level_01", algorithm_ids=["extreme_point_ffd"],
            item_counts=[1], container_counts=[1], seeds=seeds,
            config_path=root / "config/level_01/default.yaml", project_root=root,
        )


def test_quality_standard_deviation_is_computed_across_seeds_not_repeats():
    import pandas as pd

    rows = []
    for seed, objective in ((7, 10.0), (11, 20.0)):
        for repeat, runtime in ((1, 1.0), (2, 2.0)):
            rows.append({
                "level": "level_01", "algorithm": "example", "item_count": 1,
                "container_count": 1, "random_seed": seed, "repeat": repeat,
                "success": True, "status": "FEASIBLE", "algorithm_runtime_seconds": runtime,
                "wall_runtime_seconds": runtime, "objective_value": objective,
                "used_container_count": 1.0, "total_container_cost": objective,
                "occupied_bounding_volume_mm3": objective, "coordinate_compactness_mm": objective,
                "placement_signature": f"{seed}",
            })
    summary = _aggregate(pd.DataFrame(rows)).iloc[0]
    assert summary.objective_mean == 15.0
    assert summary.objective_std == pytest.approx(7.0710678118654755)
    assert summary.run_count == 4
    assert summary.seed_count == 2
    assert summary.repeats_per_seed == 2


def test_named_suite_config_declares_a_level_specific_fair_protocol(root: Path):
    suite = load_benchmark_suite(root / "config/level_01/benchmarks/core_local.yaml")

    assert suite.level_id == "level_01"
    assert suite.suite_id == "level_01_core_local_v2"
    assert [value.scenario_id for value in suite.scenarios] == [
        "small_random_i10_c3", "medium_random_i20_c5", "diverse_volume_i40_c8",
        "payload_heavy_i40_c8", "volume_heavy_i100_c12",
    ]
    assert len(suite.algorithms) == len(set(suite.algorithms))
    assert suite.seeds == (7, 11, 19)
    assert suite.scenarios[0].item_selection_strategy == "stable_random"
    assert suite.scenarios[0].item_selection_seed == 101
    assert "milp_big_m" in suite.scenarios[0].algorithm_ids
    assert all("milp_big_m" not in scenario.algorithm_ids for scenario in suite.scenarios[1:])


def test_level2_suite_separates_exact_reference_and_heuristic_scale(root: Path):
    suite = load_benchmark_suite(root / "config/level_02/benchmarks/core_local.yaml")
    assert suite.level_id == "level_02"
    assert suite.suite_id == "level_02_core_local_v1"
    assert [value.scenario_id for value in suite.scenarios] == [
        "exact_reference_i3_c2", "practical_i20_c5", "heuristic_scale_i50_c5",
    ]
    assert "milp_big_m" in suite.scenarios[0].algorithm_ids
    assert "milp_big_m" in suite.scenarios[1].algorithm_ids
    assert "milp_big_m" not in suite.scenarios[2].algorithm_ids


def test_level2_ffd_promotion_suite_declares_profile_matrix_and_repeats(root: Path):
    suite = load_benchmark_suite(root / "config/level_02/benchmarks/ffd_baseline_local.yaml")
    assert suite.level_id == "level_02"
    assert suite.suite_id == "level_02_ffd_baseline_local_v1"
    assert suite.seeds == (42,)
    assert suite.repeats == 3
    assert len(suite.scenarios) == 9
    assert suite.scenarios[0].algorithm_ids == ("extreme_point_ffd", "milp_big_m")
    assert all(
        scenario.algorithm_ids == ("extreme_point_ffd",)
        for scenario in suite.scenarios[1:]
    )
    assert {scenario.item_selection_strategy for scenario in suite.scenarios} == {
        "prefix", "stable_random", "volume_stratified", "largest_volume", "heaviest",
    }


def test_level3_ffd_baseline_suite_declares_deterministic_orientation_protocol(root: Path):
    suite = load_benchmark_suite(root / "config/level_03/benchmarks/ffd_baseline_local.yaml")

    assert suite.level_id == "level_03"
    assert suite.suite_id == "level_03_ffd_baseline_local_v1"
    assert suite.algorithms == ("extreme_point_ffd",)
    assert suite.seeds == (42,)
    assert suite.repeats == 3
    assert [scenario.scenario_id for scenario in suite.scenarios] == [
        "sanity_prefix_i3_c2", "practical_prefix_i20_c5", "stable_random_101_i20_c5",
        "diverse_volume_i40_c8", "scale_prefix_i100_c12",
    ]


def test_level3_core_heuristic_suite_compares_only_shared_level3_inputs(root: Path):
    suite = load_benchmark_suite(root / "config/level_03/benchmarks/core_heuristics_local.yaml")

    assert suite.level_id == "level_03"
    assert suite.suite_id == "level_03_core_heuristics_local_v1"
    assert suite.algorithms == (
        "extreme_point_ffd", "extreme_point_best_fit", "extreme_point_hill_climbing",
        "extreme_point_simulated_annealing", "maximal_space_best_fit",
    )
    assert suite.repeats == 3
    assert suite.scenarios[0].algorithm_ids == suite.algorithms
    assert suite.scenarios[-1].algorithm_ids == (
        "extreme_point_ffd", "extreme_point_best_fit", "maximal_space_best_fit",
    )


def test_level3_ffd_repeats_persist_horizontal_orientation_profile(root: Path, tmp_path: Path):
    config = load_config(root / "config/level_03/default.yaml")
    config["paths"].update({
        "raw_items_csv": str(root / "data/raw/dataset_small_items_original.csv"),
        "processed_dir": str(tmp_path / "processed/level_03"),
        "manifest_json": str(tmp_path / "processed/level_03/latest_manifest.json"),
        "output_root": str(tmp_path / "outputs"),
    })
    config_path = tmp_path / "level_03.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    scenario = BenchmarkScenario(
        "orientation_determinism", "Repeated horizontal-orientation FFD", 3, 2,
        algorithm_ids=("extreme_point_ffd",),
    )
    result = run_benchmark(
        level_id="level_03", algorithm_ids=["extreme_point_ffd"],
        item_counts=[3], container_counts=[2], seeds=[42], repeats=3,
        config_path=config_path, project_root=root, scenarios=[scenario],
        suite_id="orientation_determinism_test",
    )

    assert result.successful
    assert result.results["placement_signature"].nunique() == 1
    assert result.results["objective_value"].nunique() == 1
    assert set(result.results["orientation_profile"]) == {"horizontal_rotatable"}
    assert set(result.results["feasibility_policy"]) == {
        "horizontal_orientation_geometry_payload_exact_support",
    }
    assert result.results["orientation_candidates_evaluated"].min() >= 3


def test_level2_ffd_repeats_are_deterministic_on_same_input(root: Path, tmp_path: Path):
    config = load_config(root / "config/level_02/default.yaml")
    config["paths"]["raw_items_csv"] = str(root / "data/raw/dataset_small_items_original.csv")
    config["paths"]["processed_dir"] = str(tmp_path / "processed/level_02")
    config["paths"]["manifest_json"] = str(tmp_path / "processed/level_02/latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / "outputs")
    config_path = tmp_path / "level_02.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    scenario = BenchmarkScenario(
        "ffd_determinism", "Repeated deterministic Level 2 FFD", 3, 2,
        algorithm_ids=("extreme_point_ffd",),
    )
    result = run_benchmark(
        level_id="level_02", algorithm_ids=["extreme_point_ffd"],
        item_counts=[3], container_counts=[2], seeds=[42], repeats=3,
        config_path=config_path, project_root=root, scenarios=[scenario],
        suite_id="ffd_determinism_test",
    )
    assert result.successful
    assert result.results["placement_signature"].nunique() == 1
    assert result.results["objective_value"].nunique() == 1
    assert set(result.results["feasibility_policy"]) == {
        "fixed_orientation_geometry_payload_exact_support",
    }
    assert result.results["minimum_exact_support_ratio"].min() >= 0.8


def test_scenario_rows_share_one_input_fingerprint_across_algorithms(root: Path, tmp_path: Path):
    config = load_config(root / "config/level_01/default.yaml")
    config["paths"]["raw_items_csv"] = str(root / "data/raw/dataset_small_items_original.csv")
    config["paths"]["processed_dir"] = str(tmp_path / "processed/level_01")
    config["paths"]["manifest_json"] = str(tmp_path / "processed/level_01/latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / "outputs")
    config_path = tmp_path / "level_01.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    scenario = BenchmarkScenario(
        scenario_id="fair_mini", description="One shared mini instance", item_count=1, container_count=2,
        tags=("test", "small"), item_selection_strategy="stable_random", item_selection_seed=101,
    )

    result = run_benchmark(
        level_id="level_01", algorithm_ids=["extreme_point_ffd", "extreme_point_best_fit"],
        item_counts=[1], container_counts=[2], seeds=[7, 11], config_path=config_path,
        project_root=root, scenarios=[scenario], suite_id="test_fair_suite",
    )

    assert result.successful
    assert set(result.results["scenario_id"]) == {"fair_mini"}
    assert result.results["input_fingerprint"].nunique() == 1
    assert result.results["selected_item_ids_checksum"].nunique() == 1
    assert set(result.results["item_selection_strategy"]) == {"stable_random"}
    assert set(result.summary["suite_id"]) == {"test_fair_suite"}
    assert result.summary.groupby("scenario_id")["input_fingerprint"].nunique().eq(1).all()
    snapshots = [
        pd.read_csv(Path(run_dir) / "input_snapshot/items.csv")["id_item"].tolist()
        for run_dir in result.results["experiment_run_dir"]
    ]
    assert all(value == snapshots[0] for value in snapshots)
    for run_dir in result.results["experiment_run_dir"]:
        source_manifest = json.loads((Path(run_dir) / "manifest.json").read_text(encoding="utf-8"))
        source_config = yaml.safe_load((Path(run_dir) / "resolved_config.yaml").read_text(encoding="utf-8"))
        assert source_manifest["item_selection"]["strategy"] == "stable_random"
        assert source_manifest["item_selection"]["seed"] == 101
        assert source_config["instance"]["item_selection_strategy"] == "stable_random"
        assert source_config["instance"]["item_selection_seed"] == 101


def test_scenario_algorithm_policy_restricts_milp_to_reference_case(root: Path, tmp_path: Path):
    config = load_config(root / "config/level_01/default.yaml")
    config["paths"]["raw_items_csv"] = str(root / "data/raw/dataset_small_items_original.csv")
    config["paths"]["processed_dir"] = str(tmp_path / "processed/level_01")
    config["paths"]["manifest_json"] = str(tmp_path / "processed/level_01/latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / "outputs")
    config_path = tmp_path / "level_01.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    scenarios = [
        BenchmarkScenario(
            "reference", "Exact reference", 1, 2,
            algorithm_ids=("milp_big_m", "extreme_point_ffd"),
        ),
        BenchmarkScenario(
            "scale", "Heuristic-only scale case", 2, 2,
            algorithm_ids=("extreme_point_ffd",), item_selection_strategy="heaviest",
        ),
    ]

    result = run_benchmark(
        level_id="level_01", algorithm_ids=["milp_big_m", "extreme_point_ffd"],
        item_counts=[1], container_counts=[2], seeds=[7], config_path=config_path,
        project_root=root, scenarios=scenarios, suite_id="policy_test",
    )

    assert result.successful
    assert len(result.results) == 3
    assert set(result.results.loc[result.results.algorithm == "milp_big_m", "scenario_id"]) == {"reference"}
    assert set(result.results.loc[result.results.scenario_id == "scale", "algorithm"]) == {"extreme_point_ffd"}
    request = json.loads((result.run_dir / "benchmark/request.json").read_text(encoding="utf-8"))
    policies = {value["scenario_id"]: value["algorithms"] for value in request["scenarios"]}
    assert policies == {
        "reference": ["milp_big_m", "extreme_point_ffd"],
        "scale": ["extreme_point_ffd"],
    }
