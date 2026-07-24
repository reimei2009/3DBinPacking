from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from container_packing.data_loader import load_config
from container_packing.levels.level_05_validation import validate_load_bearing
from container_packing.levels.load_bearing import LoadBearingAttributes
from container_packing.levels.load_transfer import (
    LoadTransferError,
    evaluate_load_transfer,
)
from container_packing.schemas import Item, Placement


def _placement(
    item_id: str,
    *,
    x: float = 0,
    z: float = 0,
    length: float = 1000,
    width: float = 1000,
    height: float = 100,
    weight: float = 10,
) -> Placement:
    return Placement(
        item_id, "C1", x, 0, z, length, width, height, weight, "XYZ"
    )


def _item(item_id: str, weight: float = 10) -> Item:
    return Item(item_id, 1000, 1000, 100, weight)


def _strength(*item_ids: str, capacity: float = 1000) -> dict[str, LoadBearingAttributes]:
    return {
        item_id: LoadBearingAttributes(
            item_id, capacity, False, "test_fixture"
        )
        for item_id in item_ids
    }


def _contract(root: Path) -> dict:
    return load_config(root / "config/level_05/load_bearing_rules.yaml")


def test_single_floor_item_has_no_transfer_edges() -> None:
    placement = _placement("BOTTOM")
    evaluation = evaluate_load_transfer(
        [placement], _strength("BOTTOM"), epsilon_mm=1e-4
    )

    assert evaluation.edges == ()
    assert evaluation.records[0].load_above_kg == 0
    assert evaluation.records[0].total_transmitted_load_kg == 10


def test_three_layer_chain_propagates_descendant_load_recursively() -> None:
    placements = [
        _placement("BOTTOM", z=0),
        _placement("MIDDLE", z=100),
        _placement("TOP", z=200),
    ]
    evaluation = evaluate_load_transfer(
        placements, _strength("BOTTOM", "MIDDLE", "TOP"), epsilon_mm=1e-4
    )
    records = {value.item_id: value for value in evaluation.records}
    edges = {
        (value.supporter_item_id, value.child_item_id): value
        for value in evaluation.edges
    }

    assert records["TOP"].total_transmitted_load_kg == 10
    assert records["MIDDLE"].load_above_kg == 10
    assert records["MIDDLE"].total_transmitted_load_kg == 20
    assert records["BOTTOM"].load_above_kg == 20
    assert records["BOTTOM"].total_transmitted_load_kg == 30
    assert edges["MIDDLE", "TOP"].transferred_load_kg == 10
    assert edges["BOTTOM", "MIDDLE"].transferred_load_kg == 20


def test_multi_support_uses_contact_area_fractions_and_conserves_weight() -> None:
    placements = [
        _placement("LEFT", x=0, length=250),
        _placement("RIGHT", x=250, length=750),
        _placement("CHILD", z=100, weight=100),
    ]
    evaluation = evaluate_load_transfer(
        placements, _strength("LEFT", "RIGHT", "CHILD"), epsilon_mm=1e-4
    )
    edges = {value.supporter_item_id: value for value in evaluation.edges}
    records = {value.item_id: value for value in evaluation.records}

    assert edges["LEFT"].transfer_fraction == pytest.approx(0.25)
    assert edges["RIGHT"].transfer_fraction == pytest.approx(0.75)
    assert edges["LEFT"].transferred_load_kg == pytest.approx(25)
    assert edges["RIGHT"].transferred_load_kg == pytest.approx(75)
    assert (
        records["LEFT"].total_transmitted_load_kg
        + records["RIGHT"].total_transmitted_load_kg
        == pytest.approx(120)
    )


def test_non_floor_item_without_contact_is_rejected() -> None:
    with pytest.raises(LoadTransferError, match="no positive-area load supporter"):
        evaluate_load_transfer(
            [_placement("FLOATING", z=100)],
            _strength("FLOATING"),
            epsilon_mm=1e-4,
        )


def test_independent_validator_accepts_valid_recursive_chain(root: Path) -> None:
    items = [_item("BOTTOM"), _item("MIDDLE"), _item("TOP")]
    placements = [
        _placement("BOTTOM", z=0),
        _placement("MIDDLE", z=100),
        _placement("TOP", z=200),
    ]

    validation = validate_load_bearing(items, placements, _contract(root))

    assert validation.result.valid
    assert not validation.result.issues
    assert len(validation.records) == 3
    assert len(validation.edges) == 2
    assert validation.payload()["model"] == "static_vertical_contact_area_recursive_v1"


def test_level4_geometry_can_be_invalidated_by_level5_overload(root: Path) -> None:
    config = deepcopy(_contract(root))
    config["capacity_profile"]["overrides"] = [{
        "item_id": "BOTTOM",
        "max_supported_weight_kg": 15,
        "is_fragile": False,
        "load_capacity_source": "overload_fixture",
    }]
    items = [_item("BOTTOM"), _item("MIDDLE"), _item("TOP")]
    placements = [
        _placement("BOTTOM", z=0),
        _placement("MIDDLE", z=100),
        _placement("TOP", z=200),
    ]

    validation = validate_load_bearing(items, placements, config)

    assert not validation.result.valid
    assert {value.code for value in validation.result.issues} == {
        "LOAD_CAPACITY_EXCEEDED"
    }
    bottom = next(value for value in validation.records if value.item_id == "BOTTOM")
    assert bottom.load_above_kg == 20
    assert bottom.safety_margin_kg == -5


def test_fragile_item_cannot_carry_a_child(root: Path) -> None:
    config = deepcopy(_contract(root))
    config["capacity_profile"]["overrides"] = [{
        "item_id": "BOTTOM",
        "max_supported_weight_kg": 0,
        "is_fragile": True,
        "load_capacity_source": "fragile_fixture",
    }]

    validation = validate_load_bearing(
        [_item("BOTTOM"), _item("TOP")],
        [_placement("BOTTOM"), _placement("TOP", z=100)],
        config,
    )

    assert not validation.result.valid
    assert {value.code for value in validation.result.issues} == {
        "LOAD_CAPACITY_EXCEEDED", "FRAGILE_ITEM_CARRYING_LOAD",
    }


def test_validator_reports_malformed_load_graph_without_solver_state(root: Path) -> None:
    validation = validate_load_bearing(
        [_item("FLOATING")],
        [_placement("FLOATING", z=100)],
        _contract(root),
    )

    assert not validation.result.valid
    assert [value.code for value in validation.result.issues] == [
        "LOAD_GRAPH_INVALID"
    ]


def test_validator_rejects_solver_weight_that_differs_from_source(root: Path) -> None:
    validation = validate_load_bearing(
        [_item("ITEM", weight=10)],
        [_placement("ITEM", weight=9)],
        _contract(root),
    )

    assert not validation.result.valid
    assert [value.code for value in validation.result.issues] == [
        "LOAD_WEIGHT_MISMATCH"
    ]
