from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from container_packing.cli import main
from container_packing.data_loader import load_config
from container_packing.experiments.contracts import ExperimentRequest
from container_packing.experiments.runner import run_experiment
from container_packing.levels.registry import get_level, list_levels


ALGORITHM = "level_08_fixture_validation_bundle"
BASELINE = "extreme_point_best_fit_delivery_baseline_fixture"
AWARE = "extreme_point_best_fit_delivery_aware_fixture"
FFD_NEGATIVE_CONTROL = "extreme_point_ffd_delivery_negative_control_fixture"
FFD_AWARE = "extreme_point_ffd_delivery_aware_fixture"
GENERIC_BEST_FIT = "extreme_point_best_fit_delivery"
GENERIC_FFD = "extreme_point_ffd_delivery"
SEQUENTIAL_REPLAY = "level_08_sequential_replay_fixture"


def _runtime_config(root: Path, tmp_path: Path) -> Path:
    config = deepcopy(load_config(root / "config/level_08/runtime_candidate.yaml"))
    config["paths"]["processed_dir"] = str(tmp_path / "processed")
    config["paths"]["manifest_json"] = str(tmp_path / "processed" / "latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / "outputs")
    path = tmp_path / "level_08.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def _request(config_path: Path, **overrides) -> ExperimentRequest:
    values = {
        "level_id": "level_08", "algorithm_id": ALGORITHM,
        "config_path": config_path, "item_count": 2, "container_count": 1,
        "environment": "local", "item_selection_strategy": "prefix",
        "item_selection_seed": None,
    }
    values.update(overrides)
    return ExperimentRequest(**values)


def _delivery_config(root: Path, tmp_path: Path, algorithm: str) -> Path:
    name = "delivery_best_fit_aware_fixture.yaml" if algorithm == AWARE else "delivery_best_fit_baseline_fixture.yaml"
    config = deepcopy(load_config(root / "config/level_08/experiments" / name))
    config["paths"]["processed_dir"] = str(tmp_path / algorithm / "processed")
    config["paths"]["manifest_json"] = str(tmp_path / algorithm / "processed" / "latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / algorithm / "outputs")
    path = tmp_path / f"{algorithm}.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def _multi_container_delivery_config(root: Path, tmp_path: Path, algorithm: str) -> Path:
    name = (
        "delivery_multi_stop_multi_container_aware_fixture.yaml"
        if algorithm == AWARE else "delivery_multi_stop_multi_container_baseline_fixture.yaml"
    )
    config = deepcopy(load_config(root / "config/level_08/experiments" / name))
    config["paths"]["processed_dir"] = str(tmp_path / algorithm / "processed")
    config["paths"]["manifest_json"] = str(tmp_path / algorithm / "processed" / "latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / algorithm / "outputs")
    path = tmp_path / f"multi_{algorithm}.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def _ffd_negative_control_config(root: Path, tmp_path: Path) -> Path:
    config = deepcopy(load_config(root / "config/level_08/experiments/ffd_multi_container_negative_control_fixture.yaml"))
    config["paths"]["processed_dir"] = str(tmp_path / "processed")
    config["paths"]["manifest_json"] = str(tmp_path / "processed" / "latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / "outputs")
    path = tmp_path / "ffd_negative_control.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def _ffd_aware_config(root: Path, tmp_path: Path) -> Path:
    config = deepcopy(load_config(root / "config/level_08/experiments/ffd_delivery_aware_fixture.yaml"))
    config["paths"]["processed_dir"] = str(tmp_path / "processed")
    config["paths"]["manifest_json"] = str(tmp_path / "processed" / "latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / "outputs")
    path = tmp_path / "ffd_aware.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def _three_stop_config(root: Path, tmp_path: Path, algorithm: str) -> Path:
    names = {
        BASELINE: "delivery_three_stop_multi_container_baseline_fixture.yaml",
        AWARE: "delivery_three_stop_multi_container_aware_fixture.yaml",
        FFD_AWARE: "ffd_delivery_three_stop_multi_container_aware_fixture.yaml",
    }
    config = deepcopy(load_config(root / "config/level_08/experiments" / names[algorithm]))
    config["paths"]["processed_dir"] = str(tmp_path / algorithm / "processed")
    config["paths"]["manifest_json"] = str(tmp_path / algorithm / "processed" / "latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / algorithm / "outputs")
    path = tmp_path / f"three_stop_{algorithm}.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def _sequential_replay_config(root: Path, tmp_path: Path) -> Path:
    config = deepcopy(load_config(root / "config/level_08/experiments/sequential_replay_fixture.yaml"))
    config["paths"]["processed_dir"] = str(tmp_path / "processed")
    config["paths"]["manifest_json"] = str(tmp_path / "processed" / "latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / "outputs")
    path = tmp_path / "sequential_replay.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def _sequential_multi_container_config(root: Path, tmp_path: Path) -> Path:
    config = deepcopy(load_config(
        root / "config/level_08/experiments/sequential_replay_multi_container_fixture.yaml"
    ))
    config["paths"]["processed_dir"] = str(tmp_path / "processed")
    config["paths"]["manifest_json"] = str(tmp_path / "processed" / "latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / "outputs")
    path = tmp_path / "sequential_multi.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def _sequential_generic_config(root: Path, tmp_path: Path) -> Path:
    config = deepcopy(load_config(
        root / "config/level_08/experiments/sequential_delivery_20_local.yaml"
    ))
    config["paths"]["processed_dir"] = str(tmp_path / "processed")
    config["paths"]["manifest_json"] = str(tmp_path / "processed" / "latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / "outputs")
    path = tmp_path / "sequential_generic.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def test_level8_cli_fixture_composes_inherited_and_unloading_evidence(root: Path, tmp_path: Path) -> None:
    result = run_experiment(_request(_runtime_config(root, tmp_path)))
    run_dir = Path(result.metadata["run_dir"])

    assert result.solve.status == "VALIDATION_ONLY"
    assert result.validation is not None and result.validation.valid
    assert result.metadata["objective_value"] is None
    assert result.metadata["lifo_noncompliant_item_count"] == 0
    assert get_level("level_08").validate_run(run_dir).valid
    for relative in (
        "solution/compound_support.csv", "solution/center_of_mass.csv",
        "solution/unloading_accessibility.csv", "solution/rehandle_plan.csv",
        "validation/balance_validation.json", "validation/unloading_validation.json",
    ):
        assert (run_dir / relative).is_file()


def test_level8_cli_fixture_is_deterministic_and_hidden_from_streamlit(root: Path, tmp_path: Path) -> None:
    config_path = _runtime_config(root, tmp_path)
    first = run_experiment(_request(config_path))
    second = run_experiment(_request(config_path))
    first_dir = Path(first.metadata["run_dir"])
    second_dir = Path(second.metadata["run_dir"])
    for relative in (
        "solution/unloading_accessibility.csv",
        "solution/rehandle_plan.csv", "validation/unloading_validation.json",
    ):
        assert (first_dir / relative).read_bytes() == (second_dir / relative).read_bytes()
    assert "level_08" in [value.level_id for value in list_levels()]
    assert "level_08" in [value.level_id for value in list_levels() if value.web_visible]


def test_level8_cli_sequential_replay_fixture_writes_and_independently_revalidates_artifacts(root: Path, tmp_path: Path) -> None:
    config_path = _sequential_replay_config(root, tmp_path)
    first = run_experiment(_request(
        config_path, algorithm_id=SEQUENTIAL_REPLAY, item_count=3, container_count=1,
    ))
    second = run_experiment(_request(
        config_path, algorithm_id=SEQUENTIAL_REPLAY, item_count=3, container_count=1,
    ))
    first_dir = Path(first.metadata["run_dir"])
    second_dir = Path(second.metadata["run_dir"])

    assert first.solve.status == "VALIDATION_ONLY"
    assert first.validation is not None and first.validation.valid
    assert first.metadata["sequential_validation_status"] == "VALID"
    assert get_level("level_08").validate_run(first_dir).valid
    for relative in (
        "simulation/simulation_plan.json", "simulation/loading_sequence.csv",
        "simulation/unloading_sequence.csv", "simulation/events.jsonl",
        "simulation/stop_summary.csv", "simulation/simulation_metrics.json",
        "simulation/simulation_validation.json",
    ):
        assert (first_dir / relative).read_bytes() == (second_dir / relative).read_bytes()
    (first_dir / "simulation" / "events.jsonl").write_text("{}\n", encoding="utf-8")
    assert not get_level("level_08").validate_run(first_dir).valid


def test_level8_multi_container_replay_opens_each_container_per_stop(
    root: Path, tmp_path: Path
) -> None:
    result = run_experiment(_request(
        _sequential_multi_container_config(root, tmp_path),
        algorithm_id=SEQUENTIAL_REPLAY,
        item_count=6,
        container_count=2,
    ))
    run_dir = Path(result.metadata["run_dir"])
    events = [
        yaml.safe_load(line)
        for line in (run_dir / "simulation/events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    opened = {
        (value["delivery_stop_id"], value["container_id"])
        for value in events if value["event_type"] == "door_opened"
    }
    closed = {
        (value["delivery_stop_id"], value["container_id"])
        for value in events if value["event_type"] == "door_closed"
    }
    assert result.validation is not None and result.validation.valid
    assert opened == closed == {
        (stop, container)
        for stop in ("STOP-A", "STOP-B", "STOP-C")
        for container in ("C1", "C2")
    }
    assert get_level("level_08").validate_run(run_dir).valid


def test_level8_generic_best_fit_opt_in_replay_is_deterministic_and_tamper_evident(
    root: Path, tmp_path: Path
) -> None:
    config_path = _sequential_generic_config(root, tmp_path)
    request = _request(
        config_path,
        algorithm_id=GENERIC_BEST_FIT,
        item_count=20,
        container_count=5,
    )
    first = run_experiment(request)
    second = run_experiment(request)
    first_dir = Path(first.metadata["run_dir"])
    second_dir = Path(second.metadata["run_dir"])
    assert first.solve.status == "FEASIBLE"
    assert first.validation is not None and first.validation.valid
    assert first.metadata["sequential_simulation_status"] == "VALID"
    for relative in (
        "simulation/simulation_plan.json",
        "simulation/events.jsonl",
        "simulation/loading_sequence.csv",
        "simulation/unloading_sequence.csv",
        "simulation/stop_summary.csv",
        "simulation/simulation_metrics.json",
        "simulation/simulation_validation.json",
    ):
        assert (first_dir / relative).read_bytes() == (second_dir / relative).read_bytes()
    assert get_level("level_08").validate_run(first_dir).valid
    (first_dir / "simulation/simulation_plan.json").write_text("{}\n", encoding="utf-8")
    assert not get_level("level_08").validate_run(first_dir).valid


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"item_count": 4}, "item_count=3"),
        ({"container_count": 2}, "container_count=1"),
        ({"environment": "kaggle"}, "environment='local'"),
    ],
)
def test_level8_sequential_replay_rejects_non_fixture_inputs(
    root: Path, tmp_path: Path, overrides: dict, message: str
) -> None:
    request_overrides = {
        "algorithm_id": SEQUENTIAL_REPLAY, "item_count": 3, "container_count": 1,
        **overrides,
    }
    with pytest.raises(ValueError, match=message):
        run_experiment(_request(_sequential_replay_config(root, tmp_path), **request_overrides))


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"item_count": 3}, "item_count=2"),
        ({"container_count": 2}, "container_count=1"),
        ({"environment": "kaggle"}, "environment='local'"),
        ({"item_selection_strategy": "stable_random"}, "prefix selection"),
        ({"item_selection_seed": 101}, "no selection seed"),
        ({"algorithm_id": "extreme_point_best_fit"}, "not compatible"),
    ],
)
def test_level8_runtime_rejects_non_fixture_overrides(
    root: Path, tmp_path: Path, overrides: dict, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        run_experiment(_request(_runtime_config(root, tmp_path), **overrides))


def test_level8_cli_list_and_run_are_available_without_web_exposure(root: Path, tmp_path: Path, capsys) -> None:
    config_path = _runtime_config(root, tmp_path)
    assert main([
        "run", "--level", "level_08", "--algorithm", ALGORITHM,
        "--config", str(config_path), "--non-interactive", "--preview-limit", "0",
    ]) == 0
    assert "VALIDATION_ONLY" in capsys.readouterr().out


def test_level8_delivery_aware_best_fit_beats_lifo_invalid_baseline(root: Path, tmp_path: Path) -> None:
    baseline = run_experiment(_request(_delivery_config(root, tmp_path, BASELINE), algorithm_id=BASELINE))
    aware = run_experiment(_request(_delivery_config(root, tmp_path, AWARE), algorithm_id=AWARE))

    assert baseline.solve.status == "INVALID_SOLUTION"
    assert baseline.validation is not None and not baseline.validation.valid
    assert baseline.metadata["objective_value"] is None
    assert {value.item_id: value.x_mm for value in baseline.placements} == {
        "EARLY-001": 150.0, "LATE-001": 0.0,
    }
    assert aware.solve.status == "FEASIBLE"
    assert aware.validation is not None and aware.validation.valid
    assert aware.solve.objective_value == 201.0
    assert {value.item_id: value.x_mm for value in aware.placements} == {
        "EARLY-001": 0.0, "LATE-001": 100.0,
    }
    assert aware.metadata["candidate_scoring_policy"] == "level_08_prospective_direct_rehandle_tiebreak_v1"
    assert aware.metadata["total_direct_rehandles"] == 0
    assert baseline.metadata["input_fingerprint"] == aware.metadata["input_fingerprint"]


def test_level8_multi_stop_multi_container_fixture_is_valid_and_deterministic(root: Path, tmp_path: Path) -> None:
    baseline = run_experiment(_request(
        _multi_container_delivery_config(root, tmp_path, BASELINE), algorithm_id=BASELINE,
        item_count=4, container_count=2,
    ))
    config_path = _multi_container_delivery_config(root, tmp_path, AWARE)
    first = run_experiment(_request(config_path, algorithm_id=AWARE, item_count=4, container_count=2))
    second = run_experiment(_request(config_path, algorithm_id=AWARE, item_count=4, container_count=2))

    assert baseline.solve.status == "INVALID_SOLUTION"
    assert first.solve.status == "FEASIBLE"
    assert first.validation is not None and first.validation.valid
    assert first.metadata["container_count"] == 2
    assert first.metadata["total_direct_rehandles"] == 0
    assert first.metadata["input_fingerprint"] == baseline.metadata["input_fingerprint"]
    assert first.metadata["input_fingerprint"] == second.metadata["input_fingerprint"]
    assert [(value.item_id, value.container_id, value.x_mm) for value in first.placements] == [
        (value.item_id, value.container_id, value.x_mm) for value in second.placements
    ]
    run_dir = Path(first.metadata["run_dir"])
    assert len((run_dir / "solution" / "center_of_mass.csv").read_text(encoding="utf-8").splitlines()) == 3
    accessibility = (run_dir / "solution" / "unloading_accessibility.csv").read_text(encoding="utf-8")
    assert "STOP-A" in accessibility and "STOP-B" in accessibility
    assert get_level("level_08").validate_run(run_dir).valid


def test_level8_ffd_negative_control_keeps_first_feasible_container(root: Path, tmp_path: Path) -> None:
    result = run_experiment(_request(
        _ffd_negative_control_config(root, tmp_path), algorithm_id=FFD_NEGATIVE_CONTROL,
        item_count=2, container_count=2,
    ))

    assert result.solve.status == "INVALID_SOLUTION"
    assert result.validation is not None and not result.validation.valid
    assert result.metadata["objective_value"] is None
    assert result.metadata["container_selection_strategy"] == "minimum_count_then_cost_subset_search"
    assert result.metadata["candidate_container_ids"] == ["C1"]
    assert {value.item_id: (value.container_id, value.x_mm) for value in result.placements} == {
        "LATE-001": ("C1", 0.0), "EARLY-001": ("C1", 150.0),
    }
    assert result.metadata["lifo_noncompliant_item_count"] == 1


def test_level8_delivery_aware_ffd_changes_only_point_inside_first_container(root: Path, tmp_path: Path) -> None:
    result = run_experiment(_request(
        _ffd_aware_config(root, tmp_path), algorithm_id=FFD_AWARE,
        item_count=2, container_count=2,
    ))

    assert result.solve.status == "FEASIBLE"
    assert result.validation is not None and result.validation.valid
    assert result.metadata["candidate_container_ids"] == ["C1"]
    assert result.metadata["delivery_container_selection_scope"] == "first_feasible_container_only"
    assert result.metadata["total_direct_rehandles"] == 0
    assert {value.item_id: (value.container_id, value.x_mm) for value in result.placements} == {
        "LATE-001": ("C1", 100.0), "EARLY-001": ("C1", 0.0),
    }


def test_level8_three_stop_multi_container_acceptance_for_best_fit_and_ffd(root: Path, tmp_path: Path) -> None:
    baseline = run_experiment(_request(
        _three_stop_config(root, tmp_path, BASELINE), algorithm_id=BASELINE,
        item_count=6, container_count=2,
    ))
    results = []
    for algorithm in (AWARE, FFD_AWARE):
        config_path = _three_stop_config(root, tmp_path, algorithm)
        first = run_experiment(_request(config_path, algorithm_id=algorithm, item_count=6, container_count=2))
        second = run_experiment(_request(config_path, algorithm_id=algorithm, item_count=6, container_count=2))
        results.append(first)
        assert first.solve.status == "FEASIBLE"
        assert first.validation is not None and first.validation.valid
        assert first.metadata["container_count"] == 2
        assert first.metadata["total_direct_rehandles"] == 0
        assert [(value.item_id, value.container_id, value.x_mm) for value in first.placements] == [
            (value.item_id, value.container_id, value.x_mm) for value in second.placements
        ]
        run_dir = Path(first.metadata["run_dir"])
        accessibility = (run_dir / "solution" / "unloading_accessibility.csv").read_text(encoding="utf-8")
        assert all(stop in accessibility for stop in ("STOP-A", "STOP-B", "STOP-C"))
        assert len((run_dir / "solution" / "center_of_mass.csv").read_text(encoding="utf-8").splitlines()) == 3
        assert get_level("level_08").validate_run(run_dir).valid

    assert baseline.solve.status == "INVALID_SOLUTION"
    assert baseline.validation is not None and not baseline.validation.valid
    assert baseline.metadata["total_direct_rehandles"] > 0
    assert baseline.metadata["input_fingerprint"] == results[0].metadata["input_fingerprint"] == results[1].metadata["input_fingerprint"]


@pytest.mark.parametrize(
    ("algorithm", "config_name"),
    [
        (GENERIC_BEST_FIT, "default.yaml"),
        (GENERIC_FFD, "ffd_delivery_local.yaml"),
    ],
)
def test_level8_generic_runtime_is_config_driven_and_records_delivery_distribution(
    root: Path, tmp_path: Path, algorithm: str, config_name: str
) -> None:
    config = deepcopy(load_config(root / "config/level_08" / (config_name if config_name == "default.yaml" else f"experiments/{config_name}")))
    config["paths"]["processed_dir"] = str(tmp_path / algorithm / "processed")
    config["paths"]["manifest_json"] = str(tmp_path / algorithm / "processed" / "latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / algorithm / "outputs")
    config["delivery_repair_max_candidates"] = 77
    config["delivery_construction_mode"] = "delivery_priority_primary"
    config_path = tmp_path / f"{algorithm}.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    result = run_experiment(_request(
        config_path, algorithm_id=algorithm, item_count=6, container_count=2,
    ))

    assert result.solve.status == "FEASIBLE"
    assert result.validation is not None and result.validation.valid
    assert result.metadata["delivery_priority_distribution"] == {1: 2, 2: 2, 3: 2}
    assert result.metadata["delivery_stop_distribution"] == {"STOP-A": 2, "STOP-B": 2, "STOP-C": 2}
    assert result.metadata["delivery_stop_count"] == 3
    assert result.metadata["delivery_pipeline_time_limit_seconds"] == 45.0
    assert result.metadata["delivery_repair_max_candidates"] == 77
    assert result.metadata["delivery_construction_mode_selected"] == "delivery_priority_primary"
    assert result.metadata["compound_item_ordering_source_field"] == "delivery_priority"
    assert get_level("level_08").validate_run(Path(result.metadata["run_dir"])).valid


@pytest.mark.parametrize("algorithm", [GENERIC_BEST_FIT, GENERIC_FFD])
def test_level8_shared_pipeline_deadline_stops_construction_before_repair(
    root: Path, tmp_path: Path, algorithm: str,
) -> None:
    config = deepcopy(load_config(root / "config/level_08/default.yaml"))
    config["paths"]["processed_dir"] = str(tmp_path / algorithm / "processed")
    config["paths"]["manifest_json"] = str(tmp_path / algorithm / "processed" / "latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / algorithm / "outputs")
    config["delivery_pipeline_time_limit_seconds"] = 0.0
    config_path = tmp_path / f"deadline_{algorithm}.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    result = run_experiment(_request(
        config_path, algorithm_id=algorithm, item_count=6, container_count=2,
    ))

    assert result.solve.status == "TIME_LIMIT"
    assert result.validation is None
    assert result.metadata["objective_value"] is None
    assert result.metadata["construction_time_limit_reached"] is True
    assert result.metadata["delivery_repair_phase"] == "skipped_construction_time_limit"
    assert result.metadata["delivery_repair_termination_reason"] == "construction_time_limit"
