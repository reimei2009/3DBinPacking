from __future__ import annotations

from copy import deepcopy
import csv
from pathlib import Path

import pytest
import yaml

from container_packing.cli import main
from container_packing.data_loader import load_config
from container_packing.experiments.contracts import ExperimentRequest
from container_packing.experiments.runner import run_experiment
from container_packing.levels.registry import get_level, list_levels


ALGORITHM = "level_07_fixture_validation_bundle"
BALANCE_ALGORITHM = "extreme_point_best_fit_balance_fixture"
BASELINE_ALGORITHM = "extreme_point_best_fit_balance_baseline_fixture"
FFD_ALGORITHM = "extreme_point_ffd_balance_fixture"
FFD_BASELINE_ALGORITHM = "extreme_point_ffd_balance_baseline_fixture"
GENERIC_BEST_FIT = "extreme_point_best_fit_balance"
GENERIC_FFD = "extreme_point_ffd_balance"


def _runtime_config(root: Path, tmp_path: Path) -> Path:
    config = deepcopy(load_config(root / "config/level_07/experimental.yaml"))
    config["paths"]["processed_dir"] = str(tmp_path / "processed")
    config["paths"]["manifest_json"] = str(tmp_path / "processed" / "latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / "outputs")
    path = tmp_path / "level_07.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return path


def _request(config_path: Path, **overrides) -> ExperimentRequest:
    values = {
        "level_id": "level_07", "algorithm_id": ALGORITHM, "config_path": config_path,
        "item_count": 4, "container_count": 1, "environment": "local",
        "item_selection_strategy": "prefix", "item_selection_seed": None,
    }
    values.update(overrides)
    return ExperimentRequest(**values)


def test_level7_cli_fixture_run_is_valid_and_revalidates(root: Path, tmp_path: Path) -> None:
    config_path = _runtime_config(root, tmp_path)

    result = run_experiment(_request(config_path))
    run_dir = Path(result.metadata["run_dir"])

    assert result.solve.status == "VALIDATION_ONLY"
    assert result.validation is not None and result.validation.valid
    assert run_dir.parent.parent.name == "level_07"
    assert result.metadata["balance_validation_status"] == "VALID"
    assert result.metadata["balanced_container_count"] == 1
    contract = load_config(config_path)["runtime_candidate"]["output"]
    for name in contract["required_solution_tables"]:
        assert (run_dir / "solution" / name).is_file()
    for name in contract["required_validation_documents"]:
        assert (run_dir / "validation" / name).is_file()
    assert get_level("level_07").validate_run(run_dir).valid


def test_level7_cli_fixture_artifacts_are_deterministic(root: Path, tmp_path: Path) -> None:
    config_path = _runtime_config(root, tmp_path)
    first = run_experiment(_request(config_path))
    second = run_experiment(_request(config_path))
    first_dir = Path(first.metadata["run_dir"])
    second_dir = Path(second.metadata["run_dir"])
    for relative in ("solution/center_of_mass.csv", "validation/balance_validation.json"):
        assert (first_dir / relative).read_bytes() == (second_dir / relative).read_bytes()


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"item_count": 3}, "item_count=4"),
        ({"container_count": 2}, "container_count=1"),
        ({"environment": "kaggle"}, "environment='local'"),
        ({"item_selection_strategy": "stable_random"}, "item_selection_strategy='prefix'"),
        ({"item_selection_seed": 101}, "no item-selection seed"),
        ({"algorithm_id": "extreme_point_ffd"}, "not compatible"),
    ],
)
def test_level7_rejects_non_fixture_overrides(
    root: Path, tmp_path: Path, overrides: dict, message: str
) -> None:
    config_path = _runtime_config(root, tmp_path)
    with pytest.raises(ValueError, match=message):
        run_experiment(_request(config_path, **overrides))


def test_level7_generic_algorithms_are_exposed_to_cli_and_web(root: Path, tmp_path: Path, capsys) -> None:
    config_path = _runtime_config(root, tmp_path)
    assert "level_07" in [value.level_id for value in list_levels()]
    assert "level_07" in [value.level_id for value in list_levels() if value.web_visible]

    assert main([
        "run", "--level", "level_07", "--config", str(config_path),
        "--non-interactive", "--preview-limit", "0",
    ]) == 0
    output = capsys.readouterr().out
    assert "VALIDATION_ONLY" in output
    assert "COG validation: VALID" in output
    assert "Balanced containers: 1 balanced / 0 unbalanced" in output


@pytest.mark.parametrize("algorithm_id", [GENERIC_BEST_FIT, GENERIC_FFD])
def test_level7_generic_runtime_accepts_non_fixture_input(
    root: Path, tmp_path: Path, algorithm_id: str
) -> None:
    config = deepcopy(load_config(root / "config/level_07/default.yaml"))
    config["paths"]["processed_dir"] = str(tmp_path / f"processed_{algorithm_id}")
    config["paths"]["manifest_json"] = str(tmp_path / f"processed_{algorithm_id}" / "latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / "outputs")
    config["project"]["algorithm_id"] = algorithm_id
    config_path = tmp_path / f"{algorithm_id}.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    request = ExperimentRequest(
        "level_07", algorithm_id, config_path, 10, 3,
        environment="local", item_selection_strategy="prefix",
    )
    first = run_experiment(request)
    second = run_experiment(request)

    assert first.solve.status == "FEASIBLE"
    assert first.validation is not None and first.validation.valid
    assert first.placements == second.placements
    assert first.metadata["balance_validation_status"] == "VALID"
    assert first.metadata["balance_pipeline"] == "level_06_compact_then_local_cog_repair_v2"
    assert first.metadata["balance_repair_phase"] == "baseline_valid"
    assert first.metadata["balance_repair_attempts"] == 0
    assert 0 < first.metadata["balance_repair_time_limit_seconds"] <= 45
    assert first.metadata["balance_pipeline_time_limit_seconds"] == 45
    assert first.metadata["balance_outcome_class"] == "VALID_FIXED_CONTAINER"
    assert first.metadata["balance_repair_fixed_subset_seconds"] == 10
    assert 0 < first.metadata["balance_repair_lns_seconds"] <= 30
    assert 0 < first.metadata["balance_repair_extra_container_seconds"] <= 5
    assert (
        first.metadata["balance_repair_fixed_subset_seconds"]
        + first.metadata["balance_repair_lns_seconds"]
        + first.metadata["balance_repair_extra_container_seconds"]
        <= first.metadata["balance_repair_time_limit_seconds"] + 1e-9
    )
    assert first.metadata["algorithm_runtime_seconds"] >= first.metadata["balance_pipeline_runtime_seconds"]
    assert first.metadata["balance_baseline_runtime_seconds"] <= first.metadata["balance_pipeline_runtime_seconds"]
    run_dir = Path(first.metadata["run_dir"])
    assert (run_dir / "solution" / "center_of_mass.csv").is_file()
    assert (run_dir / "validation" / "balance_validation.json").is_file()
    assert get_level("level_07").validate_run(run_dir).valid


def test_level7_generic_local_repair_fixes_unbalanced_baseline(
    root: Path, tmp_path: Path,
) -> None:
    config = deepcopy(load_config(
        root / "config/level_07/experiments/balance_aware_best_fit_fixture.yaml"
    ))
    config["project"]["algorithm_id"] = GENERIC_BEST_FIT
    config["paths"]["processed_dir"] = str(tmp_path / "processed_repair")
    config["paths"]["manifest_json"] = str(
        tmp_path / "processed_repair" / "latest_manifest.json"
    )
    config["paths"]["output_root"] = str(tmp_path / "outputs")
    config["algorithms"][GENERIC_BEST_FIT] = deepcopy(
        load_config(root / "config/level_07/default.yaml")["algorithms"][
            GENERIC_BEST_FIT
        ]
    )
    config_path = tmp_path / "repair.yaml"
    config_path.write_text(
        yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
    )

    result = run_experiment(ExperimentRequest(
        "level_07", GENERIC_BEST_FIT, config_path, 3, 1,
        environment="local", item_selection_strategy="prefix",
    ))

    assert result.solve.status == "FEASIBLE"
    assert result.validation is not None and result.validation.valid
    assert result.metadata["balance_repair_phase"] == "repair_valid_local"
    assert result.metadata["balance_repair_final_container_count"] == 1
    assert result.metadata["balance_repair_candidates_evaluated"] > 0
    assert result.metadata["balance_repair_accepted_moves"]


def test_level7_balance_aware_best_fit_selects_balanced_fixture(root: Path, tmp_path: Path) -> None:
    config = deepcopy(load_config(root / "config/level_07/experiments/balance_aware_best_fit_fixture.yaml"))
    config["paths"]["processed_dir"] = str(tmp_path / "processed")
    config["paths"]["manifest_json"] = str(tmp_path / "processed/latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / "outputs")
    config_path = tmp_path / "balance_fixture.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    request = ExperimentRequest(
        "level_07", BALANCE_ALGORITHM, config_path, 3, 1,
        environment="local", item_selection_strategy="prefix",
    )
    first = run_experiment(request)
    second = run_experiment(request)
    assert first.solve.status == "FEASIBLE"
    assert first.validation is not None and first.validation.valid
    top = next(value for value in first.placements if value.item_id == "TOP")
    assert (top.x_mm, top.y_mm, top.z_mm) == (200.0, 0.0, 100.0)
    assert first.metadata["candidate_scoring_policy"].startswith("level_07_prospective")
    assert first.metadata["balance_validation_status"] == "VALID"
    assert first.metadata["balance_construction_mode"] == "soft_tiebreak_final_validation_hard"
    assert get_level("level_07").validate_run(Path(first.metadata["run_dir"])).valid
    assert first.placements == second.placements


def test_level7_baseline_best_fit_is_invalid_on_the_same_balance_fixture(root: Path, tmp_path: Path) -> None:
    config = deepcopy(load_config(root / "config/level_07/experiments/balance_baseline_best_fit_fixture.yaml"))
    config["paths"]["processed_dir"] = str(tmp_path / "processed")
    config["paths"]["manifest_json"] = str(tmp_path / "processed/latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / "outputs")
    config_path = tmp_path / "balance_baseline_fixture.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    result = run_experiment(ExperimentRequest(
        "level_07", BASELINE_ALGORITHM, config_path, 3, 1,
        environment="local", item_selection_strategy="prefix",
    ))
    run_dir = Path(result.metadata["run_dir"])
    top = next(value for value in result.placements if value.item_id == "TOP")
    assert result.solve.status == "FEASIBLE"
    assert result.validation is not None and not result.validation.valid
    assert result.metadata["status"] == "INVALID_SOLUTION"
    assert (top.x_mm, top.y_mm, top.z_mm) == (0.0, 0.0, 100.0)
    assert result.metadata["candidate_scoring_policy"] == "extreme_point_best_fit_default_v1"
    assert result.metadata["balance_validation_status"] == "INVALID"
    assert (run_dir / "solution/placements.csv").is_file()
    assert (run_dir / "solution/center_of_mass.csv").is_file()
    assert (run_dir / "validation/balance_validation.json").is_file()
    assert not get_level("level_07").validate_run(run_dir).valid


def _run_balance_profile(
    root: Path,
    tmp_path: Path,
    config_name: str,
    algorithm_id: str,
    *,
    item_count: int = 3,
    container_count: int = 1,
):
    config = deepcopy(load_config(root / "config/level_07/experiments" / config_name))
    config["paths"]["processed_dir"] = str(tmp_path / f"processed_{algorithm_id}")
    config["paths"]["manifest_json"] = str(tmp_path / f"processed_{algorithm_id}/latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / f"outputs_{algorithm_id}")
    config_path = tmp_path / f"{algorithm_id}_{config_name}"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return run_experiment(ExperimentRequest(
        "level_07", algorithm_id, config_path, item_count, container_count,
        environment="local", item_selection_strategy="prefix",
    ))


def test_level7_right_heavy_profile_selects_left_for_both_constructors(root: Path, tmp_path: Path) -> None:
    aware = _run_balance_profile(
        root, tmp_path, "balance_right_heavy_best_fit_fixture.yaml", BALANCE_ALGORITHM
    )
    baseline = _run_balance_profile(
        root, tmp_path, "balance_right_heavy_baseline_best_fit_fixture.yaml", BASELINE_ALGORITHM
    )
    for result in (aware, baseline):
        top = next(value for value in result.placements if value.item_id == "TOP")
        assert result.validation is not None and result.validation.valid
        assert top.x_mm == 0.0
        assert result.metadata["balance_validation_status"] == "VALID"


def test_level7_symmetric_profile_has_equivalent_balance_for_a_b(root: Path, tmp_path: Path) -> None:
    aware = _run_balance_profile(
        root, tmp_path, "balance_symmetric_best_fit_fixture.yaml", BALANCE_ALGORITHM
    )
    baseline = _run_balance_profile(
        root, tmp_path, "balance_symmetric_baseline_best_fit_fixture.yaml", BASELINE_ALGORITHM
    )
    for result in (aware, baseline):
        assert result.validation is not None and result.validation.valid
        assert result.metadata["balance_validation_status"] == "VALID"
    aware_top = next(value for value in aware.placements if value.item_id == "TOP")
    baseline_top = next(value for value in baseline.placements if value.item_id == "TOP")
    assert aware_top == baseline_top


def test_level7_balance_aware_ffd_selects_balanced_side_within_first_container(root: Path, tmp_path: Path) -> None:
    aware = _run_balance_profile(root, tmp_path, "ffd_balance_aware_fixture.yaml", FFD_ALGORITHM)
    baseline = _run_balance_profile(root, tmp_path, "ffd_balance_baseline_fixture.yaml", FFD_BASELINE_ALGORITHM)

    aware_top = next(value for value in aware.placements if value.item_id == "TOP")
    baseline_top = next(value for value in baseline.placements if value.item_id == "TOP")
    assert aware.solve.status == "FEASIBLE"
    assert aware.validation is not None and aware.validation.valid
    assert (aware_top.x_mm, aware_top.y_mm, aware_top.z_mm) == (200.0, 0.0, 100.0)
    assert aware.metadata["first_fit_candidate_selection_policy"].startswith("level_07_first_feasible")
    assert aware.metadata["balance_construction_mode"].startswith("first_feasible_container")
    assert aware.metadata["balance_validation_status"] == "VALID"
    assert baseline.solve.status == "FEASIBLE"
    assert baseline.validation is not None and not baseline.validation.valid
    assert baseline.metadata["status"] == "INVALID_SOLUTION"
    assert (baseline_top.x_mm, baseline_top.y_mm, baseline_top.z_mm) == (0.0, 0.0, 100.0)
    assert baseline.metadata["first_fit_candidate_selection_policy"] == "extreme_point_first_fit_default_v1"


def test_level7_balance_aware_ffd_handles_right_heavy_and_symmetric_profiles(root: Path, tmp_path: Path) -> None:
    right = _run_balance_profile(root, tmp_path, "ffd_balance_right_heavy_aware_fixture.yaml", FFD_ALGORITHM)
    symmetric_aware = _run_balance_profile(root, tmp_path, "ffd_balance_symmetric_aware_fixture.yaml", FFD_ALGORITHM)
    symmetric_baseline = _run_balance_profile(
        root, tmp_path, "ffd_balance_symmetric_baseline_fixture.yaml", FFD_BASELINE_ALGORITHM
    )

    right_top = next(value for value in right.placements if value.item_id == "TOP")
    aware_top = next(value for value in symmetric_aware.placements if value.item_id == "TOP")
    baseline_top = next(value for value in symmetric_baseline.placements if value.item_id == "TOP")
    assert right.validation is not None and right.validation.valid
    assert right_top.x_mm == 0.0
    assert symmetric_aware.validation is not None and symmetric_aware.validation.valid
    assert symmetric_baseline.validation is not None and symmetric_baseline.validation.valid
    assert aware_top == baseline_top


def test_level7_two_container_balance_fixture_is_valid_for_best_fit_and_ffd(root: Path, tmp_path: Path) -> None:
    best_fit = _run_balance_profile(
        root, tmp_path, "balance_two_container_best_fit_fixture.yaml", BALANCE_ALGORITHM,
        item_count=2, container_count=2,
    )
    ffd = _run_balance_profile(
        root, tmp_path, "balance_two_container_ffd_fixture.yaml", FFD_ALGORITHM,
        item_count=2, container_count=2,
    )

    for result in (best_fit, ffd):
        run_dir = Path(result.metadata["run_dir"])
        assert result.solve.status == "FEASIBLE"
        assert result.validation is not None and result.validation.valid
        assert {value.container_id for value in result.placements} == {"C1", "C2"}
        assert result.metadata["balanced_container_count"] == 2
        assert result.metadata["unbalanced_container_count"] == 0
        with (run_dir / "solution/center_of_mass.csv").open(encoding="utf-8-sig", newline="") as handle:
            records = list(csv.DictReader(handle))
        assert [record["container_id"] for record in records] == ["C1", "C2"]
        assert all(record["balanced"] == "True" for record in records)
        assert (run_dir / "validation/balance_validation.json").is_file()
        assert get_level("level_07").validate_run(run_dir).valid


def test_level7_ffd_negative_control_never_escapes_first_feasible_container(root: Path, tmp_path: Path) -> None:
    result = _run_balance_profile(
        root, tmp_path, "ffd_first_fit_container_scope_negative_fixture.yaml", FFD_ALGORITHM,
        item_count=1, container_count=2,
    )
    run_dir = Path(result.metadata["run_dir"])

    assert result.solve.status == "FEASIBLE"
    assert result.validation is not None and not result.validation.valid
    assert result.metadata["status"] == "INVALID_SOLUTION"
    assert result.placements[0].container_id == "C1"
    assert result.metadata["balance_container_selection_scope"] == "first_feasible_container_only"
    assert result.metadata["balance_validation_status"] == "INVALID"
    assert (run_dir / "solution/center_of_mass.csv").is_file()
    assert (run_dir / "validation/balance_validation.json").is_file()
    assert not get_level("level_07").validate_run(run_dir).valid
