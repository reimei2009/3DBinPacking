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
    assert "level_08" not in [value.level_id for value in list_levels() if value.web_visible]


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
