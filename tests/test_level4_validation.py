from __future__ import annotations

from pathlib import Path

from container_packing.data_loader import load_config
from container_packing.levels.level_04_validation import validate_solution
from container_packing.levels.stackability import StackParentRelation
from container_packing.schemas import Container, Item, Placement


def _item(item_id: str, code: str = "1", maximum: int = 3) -> Item:
    return Item(item_id, 10, 10, 5, 1, source={
        "stackability_code": code, "max_stackability": str(maximum),
    })


def _container() -> list[Container]:
    return [Container("C", 10, 10, 20, 20, 1)]


def _config(root: Path) -> dict:
    return load_config(root / "config/level_04/stackability_rules.yaml")


def test_level4_validator_accepts_same_group_direct_stack(root: Path) -> None:
    items = [_item("BOTTOM", maximum=2), _item("TOP", maximum=2)]
    placements = [
        Placement("BOTTOM", "C", 0, 0, 0, 10, 10, 5, 1),
        Placement("TOP", "C", 0, 0, 5, 10, 10, 5, 1),
    ]
    checked = validate_solution(
        items, _container(), placements, [StackParentRelation("BOTTOM", "TOP", "C")], _config(root),
        support_threshold=1.0,
    )

    assert checked.result.valid
    records = {record.item_id: record for record in checked.stack_records}
    assert records["BOTTOM"].stack_depth == 0
    assert records["TOP"].direct_parent_item_id == "BOTTOM"
    assert records["TOP"].stack_depth == 1
    assert records["TOP"].stack_layer_count == 2
    assert records["TOP"].max_stack_layers_effective == 2


def test_level4_validator_rejects_incompatible_stack_groups(root: Path) -> None:
    items = [_item("BOTTOM", "1"), _item("TOP", "2")]
    placements = [
        Placement("BOTTOM", "C", 0, 0, 0, 10, 10, 5, 1),
        Placement("TOP", "C", 0, 0, 5, 10, 10, 5, 1),
    ]
    checked = validate_solution(
        items, _container(), placements, [StackParentRelation("BOTTOM", "TOP", "C")], _config(root),
    )

    assert "INCOMPATIBLE_STACKABILITY_CODE" in {issue.code for issue in checked.result.issues}


def test_level4_validator_rejects_chain_above_max_stackability(root: Path) -> None:
    items = [_item("A", maximum=2), _item("B", maximum=2), _item("C", maximum=2)]
    placements = [
        Placement("A", "C", 0, 0, 0, 10, 10, 5, 1),
        Placement("B", "C", 0, 0, 5, 10, 10, 5, 1),
        Placement("C", "C", 0, 0, 10, 10, 10, 5, 1),
    ]
    checked = validate_solution(
        items, _container(), placements,
        [StackParentRelation("A", "B", "C"), StackParentRelation("B", "C", "C")], _config(root),
        support_threshold=1.0,
    )

    assert "STACK_LAYER_LIMIT_EXCEEDED" in {issue.code for issue in checked.result.issues}


def test_level4_validator_requires_explicit_parent_for_non_floor_item(root: Path) -> None:
    items = [_item("BOTTOM"), _item("TOP")]
    placements = [
        Placement("BOTTOM", "C", 0, 0, 0, 10, 10, 5, 1),
        Placement("TOP", "C", 0, 0, 5, 10, 10, 5, 1),
    ]
    checked = validate_solution(items, _container(), placements, [], _config(root))

    assert "MISSING_DECLARED_STACK_PARENT" in {issue.code for issue in checked.result.issues}


def test_level4_validator_honors_explicit_non_stackable_code(root: Path) -> None:
    config = _config(root)
    config["compatibility"]["non_stackable_codes"] = ["0"]
    items = [_item("BOTTOM", "0"), _item("TOP", "0")]
    placements = [
        Placement("BOTTOM", "C", 0, 0, 0, 10, 10, 5, 1),
        Placement("TOP", "C", 0, 0, 5, 10, 10, 5, 1),
    ]
    checked = validate_solution(
        items, _container(), placements, [StackParentRelation("BOTTOM", "TOP", "C")], config,
    )

    assert "NON_STACKABLE_ITEM_IN_STACK" in {issue.code for issue in checked.result.issues}
