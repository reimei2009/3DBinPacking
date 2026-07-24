from __future__ import annotations

import csv
from pathlib import Path

import pytest

from container_packing.data_loader import load_config
from container_packing.levels.nesting import NestingCapabilityProvider, NestingSettings, attributes_for_item
from container_packing.levels.registry import list_levels
from container_packing.schemas import Item


def _item(item_id: str, **source: object) -> Item:
    return Item(item_id, 100.0, 90.0, 80.0, 10.0, source=dict(source))


def _provider() -> NestingCapabilityProvider:
    host = attributes_for_item(
        _item(
            "HOST",
            nesting_group_id="G1",
            nesting_role="host",
            inner_length_mm="105",
            inner_width_mm="95",
            inner_height_mm="85",
            max_nesting_depth="2",
            nesting_data_source="company_v1",
        )
    )
    child = attributes_for_item(
        _item(
            "CHILD",
            nesting_group_id="G1",
            nesting_role="child",
            nesting_increment_height_mm="25",
            nesting_data_source="company_v1",
        )
    )
    return NestingCapabilityProvider({"HOST": host, "CHILD": child}, clearance_mm=2.0)


def test_explicit_compatible_relation_is_allowed() -> None:
    decision = _provider().can_nest(
        "HOST", "CHILD", child_length_mm=100, child_width_mm=90, child_height_mm=80, resulting_depth=2
    )

    assert decision.allowed is True
    assert decision.reason == "declared_compatible"
    assert decision.effective_increment_height_mm == 25.0


@pytest.mark.parametrize(
    ("parent_patch", "child_patch", "dimensions", "depth", "reason"),
    [
        ({"nesting_group_id": "G2"}, {}, (100, 90, 80), 1, "nesting_group_mismatch"),
        ({"nesting_role": "child"}, {}, (100, 90, 80), 1, "parent_role_not_host"),
        ({}, {"nesting_role": "host"}, (100, 90, 80), 1, "child_role_not_child"),
        ({}, {}, (104, 90, 80), 1, "inner_dimensions_insufficient"),
        ({}, {}, (100, 90, 80), 3, "maximum_nesting_depth_exceeded"),
    ],
)
def test_capability_rejects_incompatible_relations(
    parent_patch: dict[str, object],
    child_patch: dict[str, object],
    dimensions: tuple[float, float, float],
    depth: int,
    reason: str,
) -> None:
    host_source = {
        "nesting_group_id": "G1", "nesting_role": "host", "inner_length_mm": "105",
        "inner_width_mm": "95", "inner_height_mm": "85", "max_nesting_depth": "2",
        "nesting_data_source": "company_v1",
    }
    child_source = {
        "nesting_group_id": "G1", "nesting_role": "child", "nesting_increment_height_mm": "25",
        "nesting_data_source": "company_v1",
    }
    host_source.update(parent_patch)
    child_source.update(child_patch)
    if host_source["nesting_role"] in {"child", "both"}:
        host_source["nesting_increment_height_mm"] = "25"
    if child_source["nesting_role"] in {"host", "both"}:
        child_source.update({
            "inner_length_mm": "105", "inner_width_mm": "95",
            "inner_height_mm": "85", "max_nesting_depth": "2",
        })
    provider = NestingCapabilityProvider({
        "HOST": attributes_for_item(_item("HOST", **host_source)),
        "CHILD": attributes_for_item(_item("CHILD", **child_source)),
    }, clearance_mm=2.0)

    decision = provider.can_nest("HOST", "CHILD", child_length_mm=dimensions[0], child_width_mm=dimensions[1], child_height_mm=dimensions[2], resulting_depth=depth)

    assert decision.allowed is False
    assert decision.reason == reason


def test_legacy_nesting_height_alone_is_explicitly_inactive() -> None:
    attributes = attributes_for_item(_item("LEGACY", nesting_height_mm="45"))
    provider = NestingCapabilityProvider({"LEGACY": attributes})

    assert attributes.declared_active is False
    assert provider.can_nest(
        "LEGACY", "LEGACY", child_length_mm=90, child_width_mm=80, child_height_mm=70, resulting_depth=1
    ).reason == "nesting_disabled_undeclared"


def test_active_attributes_require_complete_role_specific_metadata() -> None:
    with pytest.raises(ValueError, match="requires inner dimensions"):
        attributes_for_item(_item("HOST", nesting_group_id="G1", nesting_role="host", nesting_data_source="company_v1"))
    with pytest.raises(ValueError, match="requires nesting_increment_height_mm"):
        attributes_for_item(_item("CHILD", nesting_group_id="G1", nesting_role="child", nesting_data_source="company_v1"))


def test_level6_config_is_data_contract_only_and_raw_public_data_is_unchanged(root: Path) -> None:
    config = load_config(root / "config/level_06/default.yaml")
    rules = load_config(root / "config/level_06/nesting_rules.yaml")
    with (root / "data/raw/dataset_small_items_original.csv").open(encoding="utf-8-sig", newline="") as handle:
        columns = next(csv.reader(handle))

    assert config["project"]["level_id"] == "level_06"
    assert config["model"]["enforce_nesting"] is False
    assert rules["status"] == "contract_and_validator_ready_experimental_runtime"
    assert rules["missing_metadata_behavior"] == "nesting_disabled_undeclared"
    assert NestingSettings.from_config(rules).clearance_mm == 0.0
    assert [definition.level_id for definition in list_levels()] == [
        "level_01", "level_02", "level_03", "level_04", "level_05", "level_06",
    ]
    assert "nesting_group_id" not in columns
    assert "nesting_height" in columns
