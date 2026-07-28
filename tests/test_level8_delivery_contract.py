from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest
import yaml

from container_packing.data_loader import load_config
from container_packing.levels.registry import list_levels
from container_packing.levels.unloading import (
    UnloadingSettings,
    assess_unloading_accessibility,
)
from container_packing.schemas import Item, Placement
from container_packing.source_adapter import SourceAdapterError, load_csv_source
from container_packing.synthetic_delivery import (
    generate_synthetic_delivery_data,
    load_synthetic_delivery_profile,
)


def _item(item_id: str, priority: int, stop: str, *, source: str = "fixture") -> Item:
    return Item(item_id, 100.0, 80.0, 60.0, 10.0, source={
        "delivery_priority": str(priority), "delivery_stop_id": stop, "delivery_data_source": source,
    })


def _placement(item_id: str, x: float, y: float = 0.0, z: float = 0.0, *, container: str = "C1") -> Placement:
    return Placement(item_id, container, x, y, z, 100.0, 80.0, 60.0, 10.0)


def _settings(root: Path) -> UnloadingSettings:
    return UnloadingSettings.from_config(load_config(root / "config/level_08/unloading_rules.yaml"))


def test_level8_contract_keeps_solver_inactive_until_explicit_runtime_promotion(root: Path) -> None:
    config = load_config(root / "config/level_08/unloading_rules.yaml")
    settings = _settings(root)

    assert config["status"] == "data_contract_only"
    assert settings.door_face == "x_min"
    assert settings.delivery_priority_direction == "ascending_is_earlier_delivery"
    assert config["output"] == {
        "accessibility_table": "unloading_accessibility.csv",
        "rehandle_table": "rehandle_plan.csv",
        "validation_document": "unloading_validation.json",
    }
    assert [value.level_id for value in list_levels()] == [
        "level_01", "level_02", "level_03", "level_04", "level_05", "level_06", "level_07", "level_08",
    ]


def test_straight_path_detects_no_blocker_and_lifo_valid_earlier_blocker(root: Path) -> None:
    items = [_item("EARLY", 1, "A"), _item("LATE", 2, "B")]
    records = assess_unloading_accessibility(items, [_placement("EARLY", 0), _placement("LATE", 100)], _settings(root))
    by_id = {record.item_id: record for record in records}

    assert by_id["EARLY"].directly_accessible
    assert by_id["LATE"].blocking_item_ids == ("EARLY",)
    assert not by_id["LATE"].directly_accessible
    assert by_id["LATE"].lifo_compliant
    assert by_id["LATE"].minimum_rehandle_count == 0


def test_later_delivery_blocker_requires_rehandle(root: Path) -> None:
    items = [_item("EARLY", 1, "A"), _item("LATE", 2, "B")]
    records = assess_unloading_accessibility(items, [_placement("EARLY", 100), _placement("LATE", 0)], _settings(root))
    early = next(record for record in records if record.item_id == "EARLY")

    assert early.blocking_item_ids == ("LATE",)
    assert early.later_priority_blocker_ids == ("LATE",)
    assert not early.lifo_compliant
    assert early.minimum_rehandle_count == 1


def test_path_ignores_partial_cross_section_and_other_container(root: Path) -> None:
    items = [_item("EARLY", 1, "A"), _item("LATE", 2, "B")]
    separate_y = assess_unloading_accessibility(items, [_placement("EARLY", 100), _placement("LATE", 0, 80)], _settings(root))
    other_container = assess_unloading_accessibility(items, [_placement("EARLY", 100), _placement("LATE", 0, container="C2")], _settings(root))

    assert next(record for record in separate_y if record.item_id == "EARLY").blocking_item_ids == ()
    assert next(record for record in other_container if record.item_id == "EARLY").blocking_item_ids == ()


def test_door_face_is_configurable_for_future_direction_changes(root: Path) -> None:
    config = load_config(root / "config/level_08/unloading_rules.yaml")
    config["unloading_policy"]["door_face"] = "x_max"
    settings = UnloadingSettings.from_config(config)
    items = [_item("EARLY", 1, "A"), _item("LATE", 2, "B")]
    records = assess_unloading_accessibility(items, [_placement("EARLY", 0), _placement("LATE", 100)], settings)
    early = next(record for record in records if record.item_id == "EARLY")

    assert early.later_priority_blocker_ids == ("LATE",)


def test_adapter_normalizes_explicit_delivery_fixture_and_preserves_extra_columns(root: Path) -> None:
    result = load_csv_source(
        root / "data/raw/level_08/unloading_semantic_fixture_items.csv",
        root / "config/common/data_sources/level_08_synthetic_delivery.yaml",
    )

    assert result.delivery_semantics == "priority_and_stop"
    assert result.delivery_data_source == "synthetic_level_08_delivery_v1"
    assert list(result.frame["delivery_priority"]) == [1, 2, 3, 2]
    assert result.frame.loc[0, "delivery_stop_id"] == "STOP-A"
    assert result.preserved_extra_columns == ("fixture_note",)


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ("A,10,9,8,1,0,S1,declared\n", "delivery_priority must be a positive integer"),
        ("A,10,9,8,1,1,S1,declared\nB,10,9,8,1,1,S2,declared\n", "maps to multiple"),
        ("A,10,9,8,1,1,,declared\n", "delivery_priority and delivery_stop_id are required"),
    ],
)
def test_adapter_rejects_invalid_or_ambiguous_delivery_metadata(tmp_path: Path, rows: str, message: str) -> None:
    source = tmp_path / "items.csv"
    source.write_text("sku,l,w,h,mass,priority,stop,provenance\n" + rows, encoding="utf-8")
    mapping = tmp_path / "mapping.yaml"
    mapping.write_text(yaml.safe_dump({
        "columns": {"id_item": "sku", "length": "l", "width": "w", "height": "h", "weight": "mass",
                    "delivery_priority": "priority", "delivery_stop_id": "stop", "delivery_data_source": "provenance"},
        "delivery": {"semantics": "priority_and_stop", "data_source": "test"},
    }), encoding="utf-8")
    with pytest.raises(SourceAdapterError, match=message):
        load_csv_source(source, mapping)


def test_missing_delivery_metadata_remains_safely_undeclared(root: Path) -> None:
    result = load_csv_source(root / "data/raw/dataset_small_items_original.csv")

    assert result.delivery_semantics == "undeclared"
    assert set(result.frame["delivery_data_source"]) == {"undeclared"}


def test_synthetic_generator_is_deterministic_and_profile_large_is_not_executed(root: Path, tmp_path: Path) -> None:
    profile = load_synthetic_delivery_profile("config/level_08/synthetic/small.yaml", root=root)
    first = generate_synthetic_delivery_data(replace(profile, output_dir=tmp_path / "one"))
    second = generate_synthetic_delivery_data(replace(profile, output_dir=tmp_path / "two"))

    assert first["item_count"] == 12
    assert first["container_count"] == 2
    assert first["item_csv_sha256"] == second["item_csv_sha256"]
    assert first["container_csv_sha256"] == second["container_csv_sha256"]
    assert len(pd.read_csv(first["item_path"])) == 12
    assert len(pd.read_csv(first["container_path"])) == 2
    assert load_synthetic_delivery_profile("config/level_08/synthetic/scale_5000_c200.yaml", root=root).item_count == 5000
