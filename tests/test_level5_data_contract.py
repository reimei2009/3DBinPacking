from __future__ import annotations

from copy import deepcopy
import csv
from pathlib import Path

import pytest

from container_packing.data_loader import load_config
from container_packing.levels.load_bearing import (
    LoadBearingSettings,
    resolve_load_bearing_attributes,
)
from container_packing.levels.registry import list_levels
from container_packing.schemas import Item


def _item(
    item_id: str = "I0001",
    *,
    weight_kg: float = 100.0,
    max_stackability: str = "4",
) -> Item:
    return Item(
        item_id,
        1000.0,
        800.0,
        600.0,
        weight_kg,
        source={
            "stackability_code": "1",
            "max_stackability": max_stackability,
        },
    )


def _contract(root: Path) -> dict:
    return load_config(root / "config/level_05/load_bearing_rules.yaml")


def test_level5_synthetic_profile_resolves_explicit_provenance(root: Path) -> None:
    resolved = resolve_load_bearing_attributes([_item(weight_kg=125.0)], _contract(root))

    value = resolved["I0001"]
    assert value.max_supported_weight_kg == 500.0
    assert value.is_fragile is False
    assert value.load_capacity_source == "synthetic_weight_factor_v1"


def test_level5_profile_does_not_infer_strength_from_max_stackability(root: Path) -> None:
    first = resolve_load_bearing_attributes(
        [_item(max_stackability="4")], _contract(root)
    )["I0001"]
    second = resolve_load_bearing_attributes(
        [_item(max_stackability="100")], _contract(root)
    )["I0001"]

    assert first == second


def test_level5_explicit_overrides_support_fragile_and_non_fragile_items(root: Path) -> None:
    config = deepcopy(_contract(root))
    config["capacity_profile"]["overrides"] = [
        {
            "item_id": "I0001",
            "is_fragile": True,
            "max_supported_weight_kg": 0,
            "load_capacity_source": "synthetic_fragile_fixture",
        },
        {
            "item_id": "I0002",
            "is_fragile": False,
            "max_supported_weight_kg": 900,
            "load_capacity_source": "synthetic_override_fixture",
        },
    ]

    resolved = resolve_load_bearing_attributes(
        [_item("I0001"), _item("I0002")], config
    )

    assert resolved["I0001"].max_supported_weight_kg == 0
    assert resolved["I0001"].is_fragile is True
    assert resolved["I0002"].max_supported_weight_kg == 900
    assert resolved["I0002"].is_fragile is False


@pytest.mark.parametrize(
    "overrides, message",
    [
        ([{"is_fragile": True}], "item_id"),
        (
            [{"item_id": "I0001"}, {"item_id": "I0001"}],
            "Duplicate Level 5 load-capacity override",
        ),
        (
            [{"item_id": "I0001", "max_supported_weight_kg": -1}],
            "finite and non-negative",
        ),
        (
            [{"item_id": "I0001", "max_supported_weight_kg": 0}],
            "non-fragile items require",
        ),
        (
            [{"item_id": "I0001", "is_fragile": "true"}],
            "must be a boolean",
        ),
        (
            [{"item_id": "I0001", "is_fragile": True, "max_supported_weight_kg": 1}],
            "fragile items must have",
        ),
    ],
)
def test_level5_contract_rejects_invalid_overrides(
    root: Path, overrides: list[dict], message: str
) -> None:
    config = deepcopy(_contract(root))
    config["capacity_profile"]["overrides"] = overrides

    with pytest.raises(ValueError, match=message):
        LoadBearingSettings.from_config(config)


def test_level5_resolver_rejects_unknown_and_duplicate_item_ids(root: Path) -> None:
    config = deepcopy(_contract(root))
    config["capacity_profile"]["overrides"] = [{"item_id": "UNKNOWN"}]
    with pytest.raises(ValueError, match="unknown items"):
        resolve_load_bearing_attributes([_item()], config)

    with pytest.raises(ValueError, match="Duplicate Level 5 load-capacity input item ID"):
        resolve_load_bearing_attributes([_item(), _item()], _contract(root))


def test_level5_contract_does_not_modify_or_extend_raw_3dbppsi_schema(root: Path) -> None:
    raw = root / "data/raw/dataset_small_items_original.csv"
    with raw.open(encoding="utf-8-sig", newline="") as handle:
        columns = next(csv.reader(handle))

    assert columns == [
        "id_item", "length", "width", "height", "weight", "nesting_height",
        "stackability_code", "forced_orientation", "max_stackability",
    ]
    assert "max_supported_weight_kg" not in columns
    assert "is_fragile" not in columns


def test_level5_contract_is_active_with_isolated_best_fit_runtime(root: Path) -> None:
    contract = _contract(root)

    assert contract["status"] == "active"
    assert contract["output"] == {
        "item_table": "load_bearing.csv",
        "edge_table": "load_transfer.csv",
        "validation_document": "load_bearing_validation.json",
    }
    assert [value.level_id for value in list_levels()] == [
        "level_01", "level_02", "level_03", "level_04", "level_05", "level_06",
    ]
