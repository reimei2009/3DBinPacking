from __future__ import annotations

from pathlib import Path

from container_packing.data_loader import load_config
from container_packing.levels.nesting import NestingSettings
from container_packing.levels.nesting_construction import construct_nesting_relations
from container_packing.levels.nesting_engine import NestingRelation
from container_packing.schemas import Item, Placement


def _item(item_id: str, length: float, width: float, height: float, **source: object) -> Item:
    return Item(item_id, length, width, height, 10.0, source=dict(source))


def _placement(item: Item, *, container_id: str = "C1") -> Placement:
    return Placement(item.item_id, container_id, 0.0, 0.0, 0.0, item.length_mm,
                     item.width_mm, item.height_mm, item.weight_kg, "XYZ")


def _settings(root: Path) -> NestingSettings:
    return NestingSettings.from_config(load_config(root / "config/level_06/nesting_rules.yaml"))


def _chain_items(*, root_depth: int = 3) -> list[Item]:
    return [
        _item("LARGE", 200, 120, 100, nesting_group_id="G1", nesting_role="both",
              inner_length_mm="180", inner_width_mm="110", inner_height_mm="90",
              max_nesting_depth=str(root_depth), nesting_increment_height_mm="30",
              nesting_data_source="fixture_v1"),
        _item("MEDIUM", 160, 100, 80, nesting_group_id="G1", nesting_role="both",
              inner_length_mm="110", inner_width_mm="90", inner_height_mm="70",
              max_nesting_depth="3", nesting_increment_height_mm="20",
              nesting_data_source="fixture_v1"),
        _item("SMALL", 100, 80, 60, nesting_group_id="G1", nesting_role="child",
              nesting_increment_height_mm="15", nesting_data_source="fixture_v1"),
    ]


def test_construction_builds_deterministic_best_fit_chain(root: Path) -> None:
    settings = _settings(root)
    items = _chain_items()
    placements = [_placement(item) for item in items]

    first = construct_nesting_relations(items, placements, settings)
    second = construct_nesting_relations(list(reversed(items)), list(reversed(placements)), settings)

    expected = (NestingRelation("LARGE", "MEDIUM", "C1"), NestingRelation("MEDIUM", "SMALL", "C1"))
    assert first.relations == expected
    assert second.relations == expected
    assert first.accepted_relation_count == 2
    assert first.metadata()["nesting_construction_policy"] == "explicit_nesting_best_fit_chain_v1"


def test_construction_rejects_incompatible_group_and_respects_root_depth(root: Path) -> None:
    settings = _settings(root)
    incompatible = _chain_items()
    incompatible[2] = _item("SMALL", 100, 80, 60, nesting_group_id="OTHER", nesting_role="child",
                            nesting_increment_height_mm="15", nesting_data_source="fixture_v1")
    rejected = construct_nesting_relations(incompatible, [_placement(item) for item in incompatible], settings)
    assert rejected.relations == (NestingRelation("LARGE", "MEDIUM", "C1"),)
    assert rejected.rejected_candidate_count >= 1

    depth_limited = _chain_items(root_depth=1)
    capped = construct_nesting_relations(depth_limited, [_placement(item) for item in depth_limited], settings)
    assert capped.relations == (NestingRelation("LARGE", "MEDIUM", "C1"),)
    assert capped.rejected_candidate_count >= 1


def test_construction_preserves_existing_relations_and_ignores_undeclared_items(root: Path) -> None:
    settings = _settings(root)
    items = _chain_items() + [_item("LEGACY", 40, 40, 40, nesting_height_mm="20")]
    placements = [_placement(item) for item in items]

    result = construct_nesting_relations(items, placements, settings,
                                         existing_relations=(NestingRelation("LARGE", "MEDIUM", "C1"),))

    assert result.relations == (
        NestingRelation("LARGE", "MEDIUM", "C1"),
        NestingRelation("MEDIUM", "SMALL", "C1"),
    )
    # ``LARGE`` remains metadata-eligible as role ``both`` but has no valid
    # host; legacy ``nesting_height`` alone is deliberately excluded.
    assert result.eligible_child_count == 2
