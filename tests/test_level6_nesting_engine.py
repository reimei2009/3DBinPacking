from __future__ import annotations

from pathlib import Path

import pytest

from container_packing.data_loader import load_config
from container_packing.levels.level_06_validation import validate_nesting
from container_packing.levels.nesting import attributes_for_item
from container_packing.levels.nesting_engine import (
    NestingEvaluationError,
    NestingRelation,
    evaluate_nesting,
)
from container_packing.schemas import Item, Placement


def _item(item_id: str, **source: object) -> Item:
    return Item(item_id, 100.0, 90.0, 80.0, 10.0, source=dict(source))


def _placement(item_id: str, *, height: float, container_id: str = "C1") -> Placement:
    return Placement(item_id, container_id, 0, 0, 0, 100, 90, height, 10, "XYZ")


def _chain() -> tuple[list[Item], list[Placement], list[NestingRelation]]:
    items = [
        _item(
            "HOST", nesting_group_id="G1", nesting_role="both", inner_length_mm="110",
            inner_width_mm="100", inner_height_mm="100", max_nesting_depth="2",
            nesting_increment_height_mm="30", nesting_data_source="fixture_v1",
        ),
        _item(
            "CHILD", nesting_group_id="G1", nesting_role="both", inner_length_mm="105",
            inner_width_mm="95", inner_height_mm="95", max_nesting_depth="2",
            nesting_increment_height_mm="20", nesting_data_source="fixture_v1",
        ),
        _item(
            "GRANDCHILD", nesting_group_id="G1", nesting_role="child",
            nesting_increment_height_mm="15", nesting_data_source="fixture_v1",
        ),
    ]
    placements = [
        _placement("HOST", height=100), _placement("CHILD", height=90),
        _placement("GRANDCHILD", height=80),
    ]
    relations = [
        NestingRelation("HOST", "CHILD", "C1"),
        NestingRelation("CHILD", "GRANDCHILD", "C1"),
    ]
    return items, placements, relations


def test_pure_engine_calculates_chain_depth_and_effective_height() -> None:
    items, placements, relations = _chain()
    attributes = {item.item_id: attributes_for_item(item) for item in items}

    evaluation = evaluate_nesting(placements, attributes, relations, clearance_mm=0)
    records = {value.item_id: value for value in evaluation.records}

    assert records["HOST"].nesting_depth == 0
    assert records["HOST"].chain_effective_height_mm == 100
    assert records["CHILD"].nesting_depth == 1
    assert records["CHILD"].vertical_contribution_height_mm == 20
    assert records["CHILD"].chain_effective_height_mm == 120
    assert records["GRANDCHILD"].nesting_depth == 2
    assert records["GRANDCHILD"].chain_effective_height_mm == 135


@pytest.mark.parametrize(
    ("relations", "message"),
    [
        ([NestingRelation("HOST", "CHILD", "C2")], "placements' container"),
        ([NestingRelation("HOST", "CHILD", "C1"), NestingRelation("HOST", "GRANDCHILD", "C1")], "multiple nested children"),
        ([NestingRelation("HOST", "CHILD", "C1"), NestingRelation("CHILD", "HOST", "C1")], "cycle"),
    ],
)
def test_engine_rejects_malformed_relation_graph(
    relations: list[NestingRelation], message: str
) -> None:
    items, placements, _ = _chain()
    attributes = {item.item_id: attributes_for_item(item) for item in items}

    with pytest.raises(NestingEvaluationError, match=message):
        evaluate_nesting(placements, attributes, relations)


def test_engine_enforces_depth_cap_from_declared_host() -> None:
    items, placements, relations = _chain()
    host = items[0]
    items[0] = _item(
        host.item_id, nesting_group_id="G1", nesting_role="both", inner_length_mm="110",
        inner_width_mm="100", inner_height_mm="100", max_nesting_depth="1",
        nesting_increment_height_mm="30", nesting_data_source="fixture_v1",
    )
    attributes = {item.item_id: attributes_for_item(item) for item in items}

    with pytest.raises(NestingEvaluationError, match="maximum_nesting_depth_exceeded"):
        evaluate_nesting(placements, attributes, relations)


def test_independent_validator_accepts_fixture_and_returns_canonical_payload() -> None:
    items, placements, relations = _chain()

    validation = validate_nesting(items, placements, relations)

    assert validation.result.valid
    assert len(validation.records) == 3
    assert validation.payload()["model"] == "explicit_nesting_chain_effective_height_v1"
    assert validation.payload()["records"][-1]["item_id"] == "HOST"


def test_independent_validator_recomputes_and_rejects_undeclared_legacy_nesting() -> None:
    items = [_item("HOST", nesting_height_mm="45"), _item("CHILD", nesting_height_mm="45")]
    placements = [_placement("HOST", height=100), _placement("CHILD", height=90)]

    validation = validate_nesting(items, placements, [NestingRelation("HOST", "CHILD", "C1")])

    assert not validation.result.valid
    assert validation.result.issues[0].code == "NESTING_RELATION_INVALID"
    assert "nesting_disabled_undeclared" in validation.result.issues[0].message


def test_level6_rules_describe_validator_without_activating_runtime(root: Path) -> None:
    rules = load_config(root / "config/level_06/nesting_rules.yaml")

    assert rules["status"] == "contract_and_validator_ready_experimental_runtime"
    assert rules["future_output"] == {
        "relation_table": "nesting_relations.csv",
        "item_table": "nesting_height.csv",
        "validation_document": "nesting_validation.json",
    }
