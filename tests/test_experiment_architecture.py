from pathlib import Path
import json

import yaml

from container_packing.algorithms.registry import get_algorithm, list_algorithms
from container_packing.data_loader import load_config
from container_packing.experiments.contracts import ExperimentRequest
from container_packing.experiments.runner import run_experiment
from container_packing.levels.registry import get_level, list_levels
from container_packing.runtime.inputs import prompt_choice, prompt_positive


def test_registry_only_exposes_runnable_implementations():
    assert [value.level_id for value in list_levels()] == ["level_01"]
    assert [value.algorithm_id for value in list_algorithms(level_id="level_01")] == [
        "extreme_point_ffd", "extreme_point_hill_climbing",
        "extreme_point_simulated_annealing", "milp_big_m",
    ]
    assert get_algorithm("milp_big_m").family == "exact_milp"
    assert get_level("level_01").supported_algorithms == (
        "milp_big_m", "extreme_point_ffd", "extreme_point_hill_climbing",
        "extreme_point_simulated_annealing",
    )
    contract = get_level("level_01").contract
    assert contract.objective[0].startswith("Primary")
    assert {value.constraint_id for value in contract.active_constraints} == {
        "exact_assignment", "container_activation", "boundaries", "pairwise_non_overlap", "payload",
    }
    assert "stability" in contract.inactive_constraints


def test_shared_interactive_inputs_are_not_level_specific():
    answers = iter(["12", "milp_big_m"])
    input_fn = lambda _: next(answers)
    assert prompt_positive("Items", 20, input_fn=input_fn) == 12
    assert prompt_choice("Algorithm", ("milp_big_m",), "milp_big_m", input_fn=input_fn) == "milp_big_m"


def test_config_inheritance(root):
    config = load_config(root / "config/level_01/experiments/milp_big_m_local.yaml")
    assert config["project"]["level_id"] == "level_01"
    assert config["solver"]["backend"] == "scipy_highs"
    assert config["environment"] == "local"
    heuristic = load_config(root / "config/level_01/experiments/extreme_point_ffd_local.yaml")
    assert heuristic["project"]["algorithm_id"] == "extreme_point_ffd"
    assert heuristic["algorithms"]["extreme_point_ffd"]["subset_enumeration_limit"] == 12
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
