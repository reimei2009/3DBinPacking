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
