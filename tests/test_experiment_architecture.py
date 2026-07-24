from pathlib import Path
import json

import yaml

from container_packing.algorithms.registry import get_algorithm, list_algorithms
from container_packing.cli import _parser, _resolve_request
from container_packing.data_loader import load_config
from container_packing.experiments.contracts import ExperimentRequest
from container_packing.experiments.runner import run_experiment
from container_packing.levels.registry import get_level, list_levels
from container_packing.runtime.inputs import prompt_choice, prompt_positive


def test_registry_only_exposes_runnable_implementations():
    assert [value.level_id for value in list_levels()] == [
        "level_01", "level_02", "level_03", "level_04", "level_05", "level_06",
    ]
    assert [value.algorithm_id for value in list_algorithms(level_id="level_01")] == [
        "extreme_point_best_fit", "extreme_point_ffd", "extreme_point_hill_climbing",
        "extreme_point_simulated_annealing", "maximal_space_best_fit", "milp_big_m",
    ]
    assert get_algorithm("milp_big_m").family == "exact_milp"
    assert get_level("level_01").supported_algorithms == (
        "milp_big_m", "extreme_point_best_fit", "extreme_point_ffd", "extreme_point_hill_climbing",
        "extreme_point_simulated_annealing", "maximal_space_best_fit",
    )
    assert [value.algorithm_id for value in list_algorithms(level_id="level_02")] == [
        "extreme_point_best_fit", "extreme_point_ffd", "extreme_point_hill_climbing",
        "extreme_point_simulated_annealing", "maximal_space_best_fit", "milp_big_m",
    ]
    assert get_level("level_02").supported_algorithms == (
        "milp_big_m", "extreme_point_best_fit", "extreme_point_ffd",
        "extreme_point_hill_climbing", "extreme_point_simulated_annealing",
        "maximal_space_best_fit",
    )
    assert [value.algorithm_id for value in list_algorithms(level_id="level_03")] == [
        "extreme_point_best_fit", "extreme_point_ffd", "extreme_point_hill_climbing",
        "extreme_point_simulated_annealing", "maximal_space_best_fit",
        "milp_big_m",
    ]
    assert get_level("level_03").supported_algorithms == (
        "milp_big_m", "extreme_point_ffd", "extreme_point_best_fit", "extreme_point_hill_climbing",
        "extreme_point_simulated_annealing", "maximal_space_best_fit",
    )
    assert [value.algorithm_id for value in list_algorithms(level_id="level_04")] == [
        "extreme_point_best_fit", "extreme_point_ffd", "extreme_point_hill_climbing",
        "extreme_point_simulated_annealing",
        "maximal_space_best_fit",
    ]
    assert get_level("level_04").supported_algorithms == (
        "extreme_point_ffd", "extreme_point_best_fit", "extreme_point_hill_climbing",
        "extreme_point_simulated_annealing",
        "maximal_space_best_fit",
    )
    assert [value.algorithm_id for value in list_algorithms(level_id="level_05")] == [
        "extreme_point_best_fit", "extreme_point_ffd", "extreme_point_hill_climbing",
        "extreme_point_simulated_annealing",
    ]
    assert get_level("level_05").supported_algorithms == (
        "extreme_point_best_fit", "extreme_point_ffd", "extreme_point_hill_climbing",
        "extreme_point_simulated_annealing",
    )
    assert [value.algorithm_id for value in list_algorithms(level_id="level_06")] == [
        "extreme_point_ffd_nesting_fixture",
    ]
    assert get_level("level_06").supported_algorithms == (
        "extreme_point_ffd_nesting_fixture",
    )
    assert get_level("level_06").contract.title.resolve("en").endswith("(experimental)")
    assert {value.symbol for value in get_level("level_05").contract.variables} >= {
        "T[i]", "L[i]",
    }
    assert {
        value.constraint_id for value in get_level("level_05").contract.active_constraints
    } >= {
        "recursive_static_load_transfer",
        "maximum_supported_weight",
        "fragile_no_supported_load",
    }
    assert {value.symbol for value in get_level("level_03").contract.variables} >= {"r[i,o]"}
    assert {value.constraint_id for value in get_level("level_03").contract.active_constraints} >= {
        "horizontal_orientation_selection", "orientation_dependent_dimensions",
    }
    assert get_level("level_02").contract.objective == get_level("level_01").contract.objective
    assert {value.symbol for value in get_level("level_02").contract.variables} >= {
        "floor[i,k]", "support_point[i,j,k,p,q]", "center_support[i,j,k]",
    }
    assert {value.constraint_id for value in get_level("level_02").contract.active_constraints} >= {
        "aggregate_volume_capacity", "global_capacity_lower_bounds",
    }
    contract = get_level("level_01").contract
    assert contract.title.resolve("vi").startswith("Level 1")
    assert contract.objective.latex == r"\min\; B\sum_{k\in K}u_k+\sum_{k\in K}c_k u_k"
    assert contract.objective.code_mapping.endswith("(objective)")
    assert {value.constraint_id for value in contract.active_constraints} == {
        "exact_assignment", "container_activation", "boundaries", "payload",
        "direction_linking", "separation_activation", "pairwise_non_overlap",
    }
    assert any(value.en == "stability" for value in contract.inactive_constraints)
    assert all(value.latex and value.code_mapping for value in contract.variables)
    assert all(value.latex and value.code_mapping for value in contract.active_constraints)


def test_shared_interactive_inputs_are_not_level_specific():
    answers = iter(["12", "milp_big_m"])
    input_fn = lambda _: next(answers)
    assert prompt_positive("Items", 20, input_fn=input_fn) == 12
    assert prompt_choice("Algorithm", ("milp_big_m",), "milp_big_m", input_fn=input_fn) == "milp_big_m"


def test_config_inheritance(root):
    level1_default = load_config(root / "config/level_01/default.yaml")
    level2_default = load_config(root / "config/level_02/default.yaml")
    level3_default = load_config(root / "config/level_03/default.yaml")
    assert level1_default["algorithms"] == level2_default["algorithms"]
    assert level2_default["support"]["threshold"] == 0.8
    assert level1_default["project"]["algorithm_id"] == "milp_big_m"
    assert level2_default["project"]["algorithm_id"] == "extreme_point_ffd"
    assert level3_default["project"]["level_id"] == "level_03"
    assert level3_default["model"]["allow_rotation"] is True
    assert level3_default["orientation"]["profile"] == "horizontal_rotatable"
    level4_default = load_config(root / "config/level_04/default.yaml")
    assert level4_default["project"]["level_id"] == "level_04"
    assert level4_default["project"]["algorithm_id"] == "extreme_point_best_fit"
    assert level4_default["model"]["enforce_stackability"] is True
    assert level4_default["algorithms"]["extreme_point_hill_climbing"] == {
        "initial_constructor": "extreme_point_best_fit",
        "repair_constructor": "extreme_point_best_fit",
        "subset_enumeration_limit": 12,
        "subset_candidate_limit": 48,
        "max_iterations": 10,
        "max_neighbors": 24,
    }
    assert level4_default["algorithms"]["extreme_point_simulated_annealing"]["initial_constructor"] == "extreme_point_best_fit"
    assert level4_default["algorithms"]["extreme_point_simulated_annealing"]["repair_constructor"] == "extreme_point_best_fit"
    assert level4_default["algorithms"]["extreme_point_simulated_annealing"]["max_iterations"] == 200
    assert level4_default["algorithms"]["extreme_point_simulated_annealing"]["initial_temperature"] == 0.05
    assert level4_default["algorithms"]["extreme_point_simulated_annealing"]["cooling_rate"] == 0.99
    level5_default = load_config(root / "config/level_05/default.yaml")
    assert level5_default["project"]["level_id"] == "level_05"
    assert level5_default["project"]["algorithm_id"] == "extreme_point_best_fit"
    assert level5_default["model"]["enforce_load_bearing"] is True
    assert level5_default["model"]["enforce_load_transfer"] is True
    level5_fast = load_config(root / "config/level_05/experiments/fast_local.yaml")
    level5_balanced = load_config(root / "config/level_05/experiments/balanced_local.yaml")
    level5_quality = load_config(root / "config/level_05/experiments/quality_local.yaml")
    assert level5_fast["project"]["algorithm_id"] == "extreme_point_best_fit"
    assert level5_balanced["project"]["algorithm_id"] == "extreme_point_hill_climbing"
    assert level5_quality["project"]["algorithm_id"] == "extreme_point_simulated_annealing"
    assert level5_quality["tuning"]["parameter_set_id"] == "p006_3f888c7c"
    assert level5_quality["algorithms"]["extreme_point_simulated_annealing"] == {
        "initial_constructor": "extreme_point_best_fit",
        "repair_constructor": "extreme_point_best_fit",
        "subset_enumeration_limit": 12,
        "subset_candidate_limit": 48,
        "max_iterations": 200,
        "max_neighbors": 48,
        "neighbors_per_iteration": 3,
        "initial_temperature": 0.05,
        "cooling_rate": 0.99,
        "minimum_temperature": 0.0001,
    }
    fast = load_config(root / "config/level_04/experiments/fast_local.yaml")
    balanced = load_config(root / "config/level_04/experiments/balanced_local.yaml")
    quality = load_config(root / "config/level_04/experiments/quality_local.yaml")
    assert fast["project"]["algorithm_id"] == "extreme_point_best_fit"
    assert balanced["project"]["algorithm_id"] == "extreme_point_hill_climbing"
    assert quality["project"]["algorithm_id"] == "extreme_point_simulated_annealing"
    assert quality["tuning"]["parameter_set_id"] == "p006_3f888c7c"
    assert quality["algorithms"]["extreme_point_simulated_annealing"]["cooling_rate"] == 0.99
    reference = load_config(root / "config/level_02/experiments/milp_big_m_reference.yaml")
    assert reference["project"]["algorithm_id"] == "milp_big_m"
    assert reference["instance"] == {
        **level2_default["instance"], "item_count": 3, "container_count": 2,
    }
    assert reference["solver"]["time_limit_seconds"] == 120
    level3_reference = load_config(root / "config/level_03/experiments/milp_big_m_reference.yaml")
    assert level3_reference["project"]["algorithm_id"] == "milp_big_m"
    assert level3_reference["instance"] == {
        **level3_default["instance"], "item_count": 3, "container_count": 2,
    }
    assert level3_reference["solver"]["time_limit_seconds"] == 60
    config = load_config(root / "config/level_01/experiments/milp_big_m_local.yaml")
    assert config["project"]["level_id"] == "level_01"
    assert config["solver"]["backend"] == "scipy_highs"
    assert config["environment"] == "local"
    heuristic = load_config(root / "config/level_01/experiments/extreme_point_ffd_local.yaml")
    assert heuristic["project"]["algorithm_id"] == "extreme_point_ffd"
    assert heuristic["algorithms"]["extreme_point_ffd"]["subset_enumeration_limit"] == 12
    best_fit = load_config(root / "config/level_01/experiments/extreme_point_best_fit_local.yaml")
    assert best_fit["project"]["algorithm_id"] == "extreme_point_best_fit"
    assert best_fit["algorithms"]["extreme_point_best_fit"]["subset_enumeration_limit"] == 12
    maximal_space = load_config(root / "config/level_01/experiments/maximal_space_best_fit_local.yaml")
    assert maximal_space["project"]["algorithm_id"] == "maximal_space_best_fit"
    assert maximal_space["algorithms"]["maximal_space_best_fit"]["subset_enumeration_limit"] == 12
    hill = load_config(root / "config/level_01/experiments/extreme_point_hill_climbing_local.yaml")
    assert hill["project"]["algorithm_id"] == "extreme_point_hill_climbing"
    assert hill["algorithms"]["extreme_point_hill_climbing"]["max_neighbors"] == 24
    annealing = load_config(root / "config/level_01/experiments/extreme_point_simulated_annealing_local.yaml")
    assert annealing["project"]["algorithm_id"] == "extreme_point_simulated_annealing"
    assert annealing["algorithms"]["extreme_point_simulated_annealing"]["cooling_rate"] == 0.97
    tuned = load_config(
        root / "config/level_01/experiments/extreme_point_simulated_annealing_tuned_i20_c5_local.yaml"
    )
    assert tuned["algorithms"]["extreme_point_simulated_annealing"]["initial_temperature"] == 0.05
    assert tuned["algorithms"]["extreme_point_simulated_annealing"]["cooling_rate"] == 0.95
    assert tuned["algorithms"]["extreme_point_simulated_annealing"]["max_iterations"] == 200
    assert tuned["tuning"]["parameter_set_id"] == "p002_1b6f7403"


def test_level2_cli_uses_configured_ffd_when_algorithm_is_omitted():
    args = _parser().parse_args([
        "run", "--level", "level_02", "--items-count", "3",
        "--containers-count", "2", "--non-interactive",
    ])
    request = _resolve_request(args)
    assert request.algorithm_id == "extreme_point_ffd"


def test_level3_cli_uses_configured_ffd_when_algorithm_is_omitted():
    args = _parser().parse_args([
        "run", "--level", "level_03", "--items-count", "3",
        "--containers-count", "2", "--non-interactive",
    ])
    request = _resolve_request(args)
    assert request.algorithm_id == "extreme_point_ffd"


def test_level4_cli_uses_configured_best_fit_when_algorithm_is_omitted():
    args = _parser().parse_args([
        "run", "--level", "level_04", "--items-count", "3",
        "--containers-count", "2", "--non-interactive",
    ])
    request = _resolve_request(args)
    assert request.algorithm_id == "extreme_point_best_fit"


def test_level5_cli_uses_configured_best_fit_when_algorithm_is_omitted():
    args = _parser().parse_args([
        "run", "--level", "level_05", "--items-count", "3",
        "--containers-count", "2", "--non-interactive",
    ])
    request = _resolve_request(args)
    assert request.algorithm_id == "extreme_point_best_fit"


def test_two_runs_are_isolated_and_complete(root: Path, tmp_path: Path):
    config = load_config(root / "config/level_01/default.yaml")
    config["paths"]["raw_items_csv"] = str(root / "data/raw/dataset_small_items_original.csv")
    config["paths"]["processed_dir"] = str(tmp_path / "processed/level_01")
    config["paths"]["manifest_json"] = str(tmp_path / "processed/level_01/latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / "outputs")
    config_path = tmp_path / "level_01.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    request = ExperimentRequest("level_01", "milp_big_m", config_path, 1, 2)
    first = run_experiment(request)
    second = run_experiment(request)
    first_dir = root / first.metadata["run_dir"] if not Path(first.metadata["run_dir"]).is_absolute() else Path(first.metadata["run_dir"])
    second_dir = root / second.metadata["run_dir"] if not Path(second.metadata["run_dir"]).is_absolute() else Path(second.metadata["run_dir"])
    assert first.metadata["run_id"] != second.metadata["run_id"]
    assert first_dir != second_dir
    for run_dir in (first_dir, second_dir):
        assert (run_dir / "manifest.json").is_file()
        assert (run_dir / "resolved_config.yaml").is_file()
        assert (run_dir / "input_snapshot/items.csv").is_file()
        assert (run_dir / "solution/placements.csv").is_file()
        assert (run_dir / "validation/validation_report.json").is_file()
        assert (run_dir / "visualization/scene.json").is_file()
        assert (run_dir / "visualization/combined_scene.html").is_file()
        manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
        scene = json.loads((run_dir / "visualization/scene.json").read_text(encoding="utf-8"))
        solver = json.loads((run_dir / "solver/solver_summary.json").read_text(encoding="utf-8"))
        log_event = json.loads((run_dir / "logs/run.log").read_text(encoding="utf-8").splitlines()[0])
        assert manifest["schema_version"] == "1.0"
        assert isinstance(manifest["git_dirty"], bool)
        assert len(manifest["source_tree_sha256"]) == 64
        assert len(manifest["resolved_config_checksum"]) == 64
        assert manifest["artifacts"]["canonical"]
        for container in scene["containers"]:
            view = f"visualization/container_{container['container_id']}.html"
            assert (run_dir / view).is_file()
            assert view in manifest["artifacts"]["derived"]
        assert solver["schema_version"] == "1.0"
        assert "run_dir" not in solver
        assert log_event["event"] == "experiment_completed"
