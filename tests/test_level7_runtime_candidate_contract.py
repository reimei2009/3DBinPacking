from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from container_packing.data_loader import load_config
from container_packing.levels.level_07_candidate_contract import load_runtime_candidate_contract
from container_packing.levels.registry import get_level, list_levels


def test_level7_runtime_candidate_is_frozen_and_registered_cli_only(root: Path) -> None:
    config = load_config(root / "config/level_07/runtime_candidate.yaml")

    contract = load_runtime_candidate_contract(config)

    assert contract.algorithm_id == "level_07_fixture_validation_bundle"
    assert contract.entry_point.endswith("level_07.run")
    assert contract.fixture_id == "declared_multi_compound_chain_and_top_balance_v1"
    assert contract.deterministic_repeats == 2
    assert contract.output_run_path == "outputs/level_07/runs/<run_id>"
    assert [value.level_id for value in list_levels()] == [
        "level_01", "level_02", "level_03", "level_04", "level_05", "level_06", "level_07",
    ]
    assert get_level("level_07").web_visible is False


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("algorithm_id", "extreme_point_best_fit", "algorithm_id"),
        ("status", "fixture_accepted_not_registered", "status"),
        ("entry_point", "other.entry", "entry_point"),
    ],
)
def test_level7_runtime_candidate_rejects_premature_promotion_fields(
    root: Path, field: str, value: str, message: str
) -> None:
    config = deepcopy(load_config(root / "config/level_07/runtime_candidate.yaml"))
    config["runtime_candidate"][field] = value

    with pytest.raises(ValueError, match=message):
        load_runtime_candidate_contract(config)


def test_level7_runtime_candidate_requires_complete_output_schema(root: Path) -> None:
    config = deepcopy(load_config(root / "config/level_07/runtime_candidate.yaml"))
    config["runtime_candidate"]["output"]["required_solution_tables"].pop()

    with pytest.raises(ValueError, match="solution-table contract"):
        load_runtime_candidate_contract(config)
