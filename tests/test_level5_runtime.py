from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest
import yaml

from container_packing.data_loader import load_config
from container_packing.cli import terminal_preview
from container_packing.experiments.contracts import ExperimentRequest
from container_packing.experiments.runner import run_experiment
from container_packing.levels.level_05_algorithms import execute_level_05
from container_packing.levels.level_05_validation import validate_load_bearing
from container_packing.schemas import Container, Item


def _item(item_id: str, weight_kg: float = 1.0) -> Item:
    return Item(
        item_id,
        10,
        10,
        5,
        weight_kg,
        source={"stackability_code": "1", "max_stackability": "3"},
    )


def _settings(root: Path) -> dict:
    return {
        "coordinate_tolerance_mm": 1e-6,
        "load_tolerance_kg": 1e-6,
        "subset_enumeration_limit": 4,
        "subset_candidate_limit": 4,
        "max_iterations": 2,
        "max_neighbors": 4,
        "neighbors_per_iteration": 2,
        "initial_temperature": 0.25,
        "cooling_rate": 0.9,
        "minimum_temperature": 0.001,
        "random_seed": 42,
        "support": {"threshold": 1.0, "epsilon_mm": 1e-4},
        "stackability": load_config(
            root / "config/level_04/stackability_rules.yaml"
        ),
        "load_bearing": load_config(
            root / "config/level_05/load_bearing_rules.yaml"
        ),
    }


@pytest.mark.parametrize(
    "algorithm_id", [
        "extreme_point_best_fit", "extreme_point_ffd",
        "extreme_point_hill_climbing",
        "extreme_point_simulated_annealing",
    ]
)
def test_level5_constructive_solver_builds_valid_load_bearing_stack(
    root: Path, algorithm_id: str
) -> None:
    items = [_item("A"), _item("B")]
    containers = [Container("C", 10, 10, 10, 10, 1)]
    settings = _settings(root)

    outcome = execute_level_05(algorithm_id, items, containers, settings)
    checked = validate_load_bearing(
        items, outcome.placements, settings["load_bearing"], epsilon_mm=1e-4
    )

    assert outcome.solve.status == "FEASIBLE"
    assert checked.result.valid
    assert len(checked.edges) == 1
    assert outcome.metadata["feasibility_policy"].endswith("_load_bearing")
    assert outcome.metadata["load_bearing_valid_candidates"] > 0


@pytest.mark.parametrize(
    "algorithm_id", [
        "extreme_point_best_fit", "extreme_point_ffd",
        "extreme_point_hill_climbing",
        "extreme_point_simulated_annealing",
    ]
)
def test_level5_constructive_solver_rejects_load_above_fragile_item(
    root: Path, algorithm_id: str
) -> None:
    items = [_item("A"), _item("B")]
    containers = [Container("C", 10, 10, 10, 10, 1)]
    settings = _settings(root)
    settings["load_bearing"] = deepcopy(settings["load_bearing"])
    settings["load_bearing"]["capacity_profile"]["overrides"] = [
        {
            "item_id": "A",
            "is_fragile": True,
            "max_supported_weight_kg": 0,
            "load_capacity_source": "fragile_test",
        }
    ]

    outcome = execute_level_05(algorithm_id, items, containers, settings)

    assert outcome.solve.status == "INFEASIBLE_HEURISTIC"
    assert outcome.metadata["load_bearing_rejected_candidates"] > 0


@pytest.mark.parametrize(
    "algorithm_id", [
        "extreme_point_best_fit", "extreme_point_ffd",
        "extreme_point_hill_climbing",
        "extreme_point_simulated_annealing",
    ]
)
def test_level5_constructive_solver_is_deterministic(
    root: Path, algorithm_id: str
) -> None:
    items = [_item("A"), _item("B")]
    containers = [Container("C", 10, 10, 10, 10, 1)]
    settings = _settings(root)

    first = execute_level_05(algorithm_id, items, containers, settings)
    second = execute_level_05(algorithm_id, items, containers, settings)

    assert first.solve.objective_value == second.solve.objective_value
    assert first.placements == second.placements


def test_level5_hill_climbing_zero_iteration_matches_best_fit(root: Path) -> None:
    items = [_item("A"), _item("B")]
    containers = [Container("C", 10, 10, 10, 10, 1)]
    settings = _settings(root)
    settings["max_iterations"] = 0

    best_fit = execute_level_05("extreme_point_best_fit", items, containers, settings)
    hill = execute_level_05("extreme_point_hill_climbing", items, containers, settings)

    assert hill.solve.status == "FEASIBLE"
    assert hill.placements == best_fit.placements
    assert hill.metadata["initial_constructor"] == "extreme_point_best_fit"
    assert hill.metadata["repair_constructor"] == "extreme_point_best_fit"
    assert hill.metadata["hill_climbing_iterations"] == 0


def test_level5_simulated_annealing_zero_iteration_matches_best_fit(root: Path) -> None:
    items = [_item("A"), _item("B")]
    containers = [Container("C", 10, 10, 10, 10, 1)]
    settings = _settings(root)
    settings["max_iterations"] = 0

    best_fit = execute_level_05("extreme_point_best_fit", items, containers, settings)
    annealing = execute_level_05(
        "extreme_point_simulated_annealing", items, containers, settings
    )

    assert annealing.solve.status == "FEASIBLE"
    assert annealing.placements == best_fit.placements
    assert annealing.metadata["initial_constructor"] == "extreme_point_best_fit"
    assert annealing.metadata["repair_constructor"] == "extreme_point_best_fit"
    assert annealing.metadata["annealing_iterations"] == 0


def test_level5_run_is_isolated_and_writes_load_artifacts(
    root: Path, tmp_path: Path
) -> None:
    config = load_config(root / "config/level_05/default.yaml")
    config["paths"]["raw_items_csv"] = str(
        root / "data/raw/dataset_small_items_original.csv"
    )
    config["paths"]["processed_dir"] = str(tmp_path / "processed/level_05")
    config["paths"]["manifest_json"] = str(
        tmp_path / "processed/level_05/latest_manifest.json"
    )
    config["paths"]["output_root"] = str(tmp_path / "outputs")
    config_path = tmp_path / "level_05.yaml"
    config_path.write_text(
        yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
    )

    result = run_experiment(
        ExperimentRequest(
            "level_05", "extreme_point_best_fit", config_path, 2, 2
        )
    )
    run_dir = Path(result.metadata["run_dir"])
    run_dir = run_dir if run_dir.is_absolute() else root / run_dir

    assert result.solve.status == "FEASIBLE"
    assert result.validation is not None and result.validation.valid
    preview = terminal_preview(result, placement_limit=0)
    assert "Support threshold: 0.8" in preview
    assert "Load capacity profile: synthetic_weight_factor_v1" in preview
    assert "Load-transfer edges:" in preview
    assert run_dir.is_relative_to(tmp_path / "outputs/level_05/runs")
    assert (run_dir / "solution/load_bearing.csv").is_file()
    assert (run_dir / "solution/load_transfer.csv").is_file()
    document = json.loads(
        (run_dir / "validation/load_bearing_validation.json").read_text(
            encoding="utf-8"
        )
    )
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    metrics = json.loads(
        (run_dir / "metrics/metrics.json").read_text(encoding="utf-8")
    )
    assert document["valid"] is True
    assert manifest["level"] == "level_05"
    assert manifest["load_bearing_contract_version"] == 1
    assert manifest["load_bearing_capacity_profile"] == "synthetic_weight_factor_v1"
    assert metrics["load_bearing_enabled"] is True
    assert metrics["load_transfer_enabled"] is True
    assert metrics["overloaded_item_count"] == 0
    assert not (tmp_path / "outputs/level_04").exists()
