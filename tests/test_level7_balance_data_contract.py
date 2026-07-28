from __future__ import annotations

from copy import deepcopy
import csv
from pathlib import Path

import pytest

from container_packing.data_loader import load_config
from container_packing.levels.load_balance import (
    ContainerBalanceSettings,
    resolve_container_balance_attributes,
)
from container_packing.levels.registry import list_levels
from container_packing.schemas import Container


def _container(
    container_id: str = "C1", *, max_weight_kg: float = 1000.0
) -> Container:
    return Container(container_id, 6000.0, 2400.0, 2600.0, max_weight_kg, 100.0)


def _contract(root: Path) -> dict:
    return load_config(root / "config/level_07/balance_rules.yaml")


def test_level7_symmetric_profile_resolves_explicit_provenance(root: Path) -> None:
    resolved = resolve_container_balance_attributes([_container()], _contract(root))

    value = resolved["C1"]
    assert value.target_longitudinal_ratio == 0.5
    assert value.target_lateral_ratio == 0.5
    assert value.max_longitudinal_offset_ratio == 0.15
    assert value.max_lateral_offset_ratio == 0.15
    assert value.balance_profile_source == "synthetic_symmetric_center_band_v1"


def test_level7_container_override_replaces_only_declared_values(root: Path) -> None:
    config = deepcopy(_contract(root))
    config["balance_profile"]["overrides"] = [{
        "container_id": "C2",
        "target_longitudinal_ratio": 0.45,
        "max_lateral_offset_ratio": 0.10,
        "balance_profile_source": "synthetic_asymmetric_fixture",
    }]

    resolved = resolve_container_balance_attributes([_container("C1"), _container("C2")], config)

    assert resolved["C2"].target_longitudinal_ratio == 0.45
    assert resolved["C2"].target_lateral_ratio == 0.5
    assert resolved["C2"].max_longitudinal_offset_ratio == 0.15
    assert resolved["C2"].max_lateral_offset_ratio == 0.10
    assert resolved["C2"].balance_profile_source == "synthetic_asymmetric_fixture"


def test_level7_profile_does_not_infer_balance_from_payload_capacity(root: Path) -> None:
    first = resolve_container_balance_attributes([_container(max_weight_kg=1000)], _contract(root))["C1"]
    second = resolve_container_balance_attributes([_container(max_weight_kg=99999)], _contract(root))["C1"]

    assert first == second


@pytest.mark.parametrize(
    "overrides, message",
    [
        ([{}], "container_id"),
        ([{"container_id": "C1"}, {"container_id": "C1"}], "Duplicate Level 7"),
        ([{"container_id": "C1", "target_lateral_ratio": 1.1}], "between 0 and 1.0"),
        ([{"container_id": "C1", "max_lateral_offset_ratio": 0.6}], "between 0 and 0.5"),
        ([{"container_id": "C1", "max_longitudinal_offset_ratio": -0.1}], "between 0 and 0.5"),
        ([{"container_id": "C1", "balance_profile_source": ""}], "non-empty string"),
    ],
)
def test_level7_contract_rejects_invalid_overrides(
    root: Path, overrides: list[dict], message: str
) -> None:
    config = deepcopy(_contract(root))
    config["balance_profile"]["overrides"] = overrides

    with pytest.raises(ValueError, match=message):
        ContainerBalanceSettings.from_config(config)


def test_level7_resolver_rejects_unknown_duplicate_and_invalid_containers(root: Path) -> None:
    config = deepcopy(_contract(root))
    config["balance_profile"]["overrides"] = [{"container_id": "UNKNOWN"}]
    with pytest.raises(ValueError, match="unknown containers"):
        resolve_container_balance_attributes([_container()], config)

    with pytest.raises(ValueError, match="Duplicate Level 7 balance input container ID"):
        resolve_container_balance_attributes([_container(), _container()], _contract(root))

    invalid = Container("C1", 0.0, 2400.0, 2600.0, 1000.0, 100.0)
    with pytest.raises(ValueError, match="length_mm"):
        resolve_container_balance_attributes([invalid], _contract(root))


def test_level7_contract_does_not_modify_or_extend_raw_3dbppsi_schema(root: Path) -> None:
    raw = root / "data/raw/dataset_small_items_original.csv"
    with raw.open(encoding="utf-8-sig", newline="") as handle:
        columns = next(csv.reader(handle))

    assert "weight" in columns
    assert "target_longitudinal_ratio" not in columns
    assert "max_lateral_offset_ratio" not in columns


def test_level7_contract_is_registered_as_a_cli_only_validation_fixture(root: Path) -> None:
    contract = _contract(root)

    assert contract["status"] == "data_contract_only"
    assert contract["output"] == {
        "item_table": "center_of_mass.csv",
        "validation_document": "balance_validation.json",
    }
    assert [value.level_id for value in list_levels()] == [
        "level_01", "level_02", "level_03", "level_04", "level_05", "level_06", "level_07", "level_08",
    ]
