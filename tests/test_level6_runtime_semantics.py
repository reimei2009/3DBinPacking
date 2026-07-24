from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from container_packing.data_loader import load_config
from container_packing.levels.nesting import NestingSettings, attributes_for_item
from container_packing.levels.nesting_engine import NestingRelation
from container_packing.levels.nesting_runtime import project_nesting_compounds
from container_packing.schemas import Item, Placement


def _fixture() -> tuple[list[Item], list[Placement], list[NestingRelation]]:
    items = [
        Item(
            "HOST", 100, 90, 80, 10,
            source={
                "nesting_group_id": "G1", "nesting_role": "host",
                "inner_length_mm": "110", "inner_width_mm": "100", "inner_height_mm": "90",
                "max_nesting_depth": "1", "nesting_data_source": "fixture_v1",
            },
        ),
        Item(
            "CHILD", 100, 90, 70, 15,
            source={
                "nesting_group_id": "G1", "nesting_role": "child",
                "nesting_increment_height_mm": "20", "nesting_data_source": "fixture_v1",
            },
        ),
        Item("STANDALONE", 40, 40, 40, 5, source={}),
    ]
    placements = [
        Placement("HOST", "C1", 0, 0, 0, 100, 90, 80, 10, "XYZ"),
        Placement("CHILD", "C1", 0, 0, 80, 100, 90, 70, 15, "XYZ"),
        Placement("STANDALONE", "C1", 120, 0, 0, 40, 40, 40, 5, "XYZ"),
    ]
    return items, placements, [NestingRelation("HOST", "CHILD", "C1")]


def test_compound_projection_uses_root_envelope_and_preserves_all_weight() -> None:
    items, placements, relations = _fixture()
    attributes = {item.item_id: attributes_for_item(item) for item in items}

    projection = project_nesting_compounds(placements, attributes, relations)
    compounds = {value.root_item_id: value for value in projection.compounds}

    nested = compounds["HOST"]
    assert nested.member_item_ids == ("HOST", "CHILD")
    assert nested.length_mm == 100
    assert nested.width_mm == 90
    assert nested.effective_height_mm == 100
    assert nested.external_weight_kg == 25
    assert "CHILD" not in compounds
    assert compounds["STANDALONE"].member_item_ids == ("STANDALONE",)
    assert compounds["STANDALONE"].effective_height_mm == 40


def test_runtime_semantics_are_versioned_and_inactive(root: Path) -> None:
    rules = load_config(root / "config/level_06/nesting_rules.yaml")

    settings = NestingSettings.from_config(rules)

    assert settings.runtime_semantics_status == "designed_not_active"
    assert rules["runtime_semantics"]["external_occupancy"] == "compound_root_effective_envelope"
    assert rules["runtime_semantics"]["load_transfer"] == "compound_weight_through_root_external_contacts"


def test_runtime_semantics_contract_rejects_unreviewed_geometry_mode(root: Path) -> None:
    rules = deepcopy(load_config(root / "config/level_06/nesting_rules.yaml"))
    rules["runtime_semantics"]["child_coordinate_mode"] = "overlap_exception"

    with pytest.raises(ValueError, match="child_coordinate_mode"):
        NestingSettings.from_config(rules)
