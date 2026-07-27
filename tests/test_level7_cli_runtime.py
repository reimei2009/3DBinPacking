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


ALGORITHM = "level_07_fixture_validation_bundle"
BALANCE_ALGORITHM = "extreme_point_best_fit_balance_fixture"
BASELINE_ALGORITHM = "extreme_point_best_fit_balance_baseline_fixture"


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


def test_level7_is_exposed_to_cli_but_not_web(root: Path, tmp_path: Path, capsys) -> None:
    config_path = _runtime_config(root, tmp_path)
    assert "level_07" in [value.level_id for value in list_levels()]
    assert "level_07" not in [value.level_id for value in list_levels() if value.web_visible]

    assert main([
        "run", "--level", "level_07", "--config", str(config_path),
        "--non-interactive", "--preview-limit", "0",
    ]) == 0
    output = capsys.readouterr().out
    assert "VALIDATION_ONLY" in output
    assert "COG validation: VALID" in output
    assert "Balanced containers: 1 balanced / 0 unbalanced" in output


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


def _run_balance_profile(root: Path, tmp_path: Path, config_name: str, algorithm_id: str):
    config = deepcopy(load_config(root / "config/level_07/experiments" / config_name))
    config["paths"]["processed_dir"] = str(tmp_path / f"processed_{algorithm_id}")
    config["paths"]["manifest_json"] = str(tmp_path / f"processed_{algorithm_id}/latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / f"outputs_{algorithm_id}")
    config_path = tmp_path / f"{algorithm_id}_{config_name}"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return run_experiment(ExperimentRequest(
        "level_07", algorithm_id, config_path, 3, 1,
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
