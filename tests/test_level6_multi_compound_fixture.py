from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from container_packing.benchmarks import run_benchmark
from container_packing.benchmarks.suites import load_benchmark_suite
from container_packing.data_loader import load_config
from container_packing.levels.level_06_pipeline import run_from_config


@pytest.mark.parametrize(
    ("algorithm_id", "config_name"),
    [
        ("extreme_point_ffd_nesting_fixture", "declared_nesting_multi_compound_fixture.yaml"),
        ("extreme_point_best_fit_nesting_fixture", "declared_nesting_multi_compound_best_fit_fixture.yaml"),
        (
            "extreme_point_hill_climbing_nesting_fixture",
            "declared_nesting_multi_compound_hill_climbing_fixture.yaml",
        ),
        (
            "extreme_point_simulated_annealing_nesting_fixture",
            "declared_nesting_multi_compound_simulated_annealing_fixture.yaml",
        ),
    ],
)
def test_multi_compound_fixture_validates_external_support_stackability_and_load_transfer(
    root: Path, tmp_path: Path, algorithm_id: str, config_name: str
) -> None:
    config = load_config(root / "config/level_06/experiments" / config_name)
    config["paths"]["processed_dir"] = str(tmp_path / "processed")
    config["paths"]["manifest_json"] = str(tmp_path / "processed/latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / "outputs")
    config_path = tmp_path / config_name
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    result = run_from_config(
        config_path, item_count=4, container_count=1, algorithm_id=algorithm_id
    )

    assert result.solve.status == "FEASIBLE"
    assert result.validation is not None and result.validation.valid
    assert result.metadata["nesting_relation_count"] == 2
    assert result.metadata["compound_count"] == 2
    assert result.metadata["maximum_nesting_depth"] == 2
    assert result.metadata["load_transfer_edge_count"] == 1
    assert result.metadata["compound_relation_graph_mode"] == "fixed_preconstructed_relations"
    assert result.metadata["compound_search_item_count"] == 2
    run_dir = Path(result.metadata["run_dir"])
    relations = pd.read_csv(run_dir / "solution/nesting_relations.csv")
    compounds = pd.read_csv(run_dir / "solution/nesting_compounds.csv")
    stacks = pd.read_csv(run_dir / "solution/stacks.csv")
    transfers = pd.read_csv(run_dir / "solution/load_transfer.csv")
    compound_validation = json.loads(
        (run_dir / "validation/compound_geometry_validation.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    solver_summary = json.loads(
        (run_dir / "solver/solver_summary.json").read_text(encoding="utf-8")
    )

    assert relations[["host_item_id", "child_item_id"]].values.tolist() == [
        ["MIDDLE-001", "CHILD-001"], ["ROOT-001", "MIDDLE-001"],
    ]
    assert set(compounds["root_item_id"]) == {"ROOT-001", "TOP-001"}
    assert compounds.loc[compounds["root_item_id"] == "ROOT-001", "effective_height_mm"].item() == 165
    top_support = next(value for value in compound_validation["support_records"] if value["root_item_id"] == "TOP-001")
    assert top_support["supporting_root_item_ids"] == ["ROOT-001"]
    assert top_support["exact_support_ratio"] == 1.0
    assert top_support["center_supported"] is True
    assert stacks.loc[stacks["item_id"] == "TOP-001", "direct_parent_item_id"].item() == "ROOT-001"
    assert transfers[["supporter_item_id", "child_item_id"]].values.tolist() == [["ROOT-001", "TOP-001"]]
    assert manifest["compound_relation_graph_mode"] == "fixed_preconstructed_relations"
    assert manifest["compound_search_item_count"] == 2
    assert solver_summary["compound_relation_graph_mode"] == "fixed_preconstructed_relations"
    assert solver_summary["compound_search_item_count"] == 2


def test_multi_compound_benchmark_shares_input_and_is_deterministic(root: Path, tmp_path: Path) -> None:
    suite = load_benchmark_suite(
        root / "config/level_06/benchmarks/compound_portfolio_fixture_local.yaml"
    )
    config = load_config(root / suite.config_path)
    config["paths"]["processed_dir"] = str(tmp_path / "processed")
    config["paths"]["manifest_json"] = str(tmp_path / "processed/latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / "outputs")
    config_path = tmp_path / "multi_compound.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    result = run_benchmark(
        level_id=suite.level_id,
        algorithm_ids=suite.algorithms,
        item_counts=[4],
        container_counts=[1],
        repeats=suite.repeats,
        seeds=suite.seeds,
        config_path=config_path,
        project_root=root,
        scenarios=suite.scenarios,
        suite_id=suite.suite_id,
    )

    assert result.successful
    assert len(result.results) == 8
    assert result.results["input_fingerprint"].nunique() == 1
    assert result.results.groupby("algorithm")["placement_signature"].nunique().eq(1).all()
    for run_dir in result.results["experiment_run_dir"]:
        path = Path(run_dir)
        assert (path / "solution/compound_support.csv").is_file()
        assert (path / "solution/stacks.csv").is_file()
        assert (path / "solution/load_transfer.csv").is_file()


def test_hill_zero_iteration_matches_best_fit_on_compound_roots(
    root: Path, tmp_path: Path
) -> None:
    config = load_config(
        root / "config/level_06/experiments/declared_nesting_multi_compound_fixture.yaml"
    )
    config["paths"]["processed_dir"] = str(tmp_path / "processed")
    config["paths"]["manifest_json"] = str(tmp_path / "processed/latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / "outputs")
    config_path = tmp_path / "multi_compound.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    best_fit = run_from_config(
        config_path,
        item_count=4,
        container_count=1,
        algorithm_id="extreme_point_best_fit_nesting_fixture",
        write_outputs=False,
    )
    hill = run_from_config(
        config_path,
        item_count=4,
        container_count=1,
        algorithm_id="extreme_point_hill_climbing_nesting_fixture",
        algorithm_parameters={"max_iterations": 0},
        write_outputs=False,
    )

    assert hill.solve.status == "FEASIBLE"
    assert hill.solve.objective_value == best_fit.solve.objective_value
    assert hill.placements == best_fit.placements
    assert hill.metadata["hill_climbing_iterations"] == 0
    assert hill.metadata["initial_constructor"] == "extreme_point_best_fit"
    assert hill.metadata["repair_constructor"] == "extreme_point_best_fit"
    assert hill.metadata["nesting_accepted_relation_count"] == 2


def test_level6_sa_uses_locked_p006_profile(root: Path) -> None:
    config = load_config(
        root
        / "config/level_06/experiments"
        / "declared_nesting_multi_compound_simulated_annealing_fixture.yaml"
    )
    settings = config["algorithms"]["extreme_point_simulated_annealing_nesting_fixture"]

    assert settings["max_iterations"] == 200
    assert settings["initial_temperature"] == 0.05
    assert settings["cooling_rate"] == 0.99
    assert settings["initial_constructor"] == "extreme_point_best_fit"
    assert settings["repair_constructor"] == "extreme_point_best_fit"
