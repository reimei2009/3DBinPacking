from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pandas as pd

from container_packing.data_loader import load_config
from container_packing.instance_data import item_selection_fingerprint, prepare_instance


def test_cross_level_enrichment_preserves_all_physical_source_rows(root: Path) -> None:
    source = pd.read_csv(
        root / "data/raw/dataset_small_items_original.csv", encoding="utf-8-sig"
    )
    enriched = pd.read_csv(
        root / "data/raw/level_08/cross_level/dataset_small_delivery_items_v1.csv",
        encoding="utf-8-sig",
    )
    physical = [
        "id_item", "length", "width", "height", "weight", "nesting_height",
        "stackability_code", "forced_orientation", "max_stackability",
    ]

    pd.testing.assert_frame_equal(source[physical], enriched[physical])
    assert len(enriched) == 501
    assert set(enriched["delivery_priority"]) == {1, 2, 3, 4, 5}
    assert (
        enriched["delivery_stop_id"]
        == enriched["delivery_priority"].map(lambda value: f"STOP-{value:03d}")
    ).all()
    assert set(enriched["delivery_data_source"]) == {
        "cross_level_declared_delivery_v1"
    }


def test_cross_level_selection_checksums_match_level7(root: Path) -> None:
    source = root / "data/raw/dataset_small_items_original.csv"
    enriched = (
        root / "data/raw/level_08/cross_level/dataset_small_delivery_items_v1.csv"
    )
    level7_mapping = root / "config/common/data_sources/3dbppsi_dataset_small.yaml"
    level8_mapping = (
        root / "config/common/data_sources/level_08_cross_level_delivery.yaml"
    )

    for strategy, seed in (("prefix", None), ("stable_random", 101)):
        level7 = item_selection_fingerprint(
            source, 20, strategy=strategy, seed=seed, mapping_path=level7_mapping
        )
        level8 = item_selection_fingerprint(
            enriched, 20, strategy=strategy, seed=seed, mapping_path=level8_mapping
        )
        assert level7["selected_item_ids"] == level8["selected_item_ids"]
        assert (
            level7["selected_item_ids_checksum"]
            == level8["selected_item_ids_checksum"]
        )


def test_cross_level_catalog_matches_level1_and_extension(root: Path) -> None:
    level1 = load_config(root / "config/level_01/default.yaml")["containers"]
    catalog = pd.read_csv(
        root / "data/raw/level_08/cross_level/container_catalog_c1_c10_v1.csv",
        encoding="utf-8-sig",
    )
    columns = [
        "container_id", "length_mm", "width_mm", "height_mm",
        "max_weight_kg", "availability", "cost",
    ]
    expected = [dict(value) for value in level1]
    while len(expected) < 10:
        previous = expected[-1]
        number = len(expected) + 1
        expected.append(
            {
                "container_id": f"C{number}",
                "length_mm": float(previous["length_mm"]) + 500,
                "width_mm": float(previous["width_mm"]) + 50,
                "height_mm": float(previous["height_mm"]) + 100,
                "max_weight_kg": float(previous["max_weight_kg"]) + 750,
                "availability": 1,
                "cost": float(previous["cost"]) + 150,
            }
        )
    expected_frame = pd.DataFrame(expected)[columns]
    pd.testing.assert_frame_equal(
        expected_frame.reset_index(drop=True),
        catalog[columns].reset_index(drop=True),
        check_dtype=False,
    )
    assert set(catalog["container_catalog_id"]) == {
        "cross_level_container_catalog_v1"
    }


def test_cross_level_profile_records_identity_in_instance_manifest(
    root: Path, tmp_path: Path
) -> None:
    config = deepcopy(
        load_config(
            root / "config/level_08/experiments/web_cross_level_comparison.yaml"
        )
    )
    config["paths"]["processed_dir"] = str(tmp_path / "processed")
    config["paths"]["manifest_json"] = str(tmp_path / "latest_manifest.json")

    manifest = prepare_instance(
        root,
        config,
        item_count=20,
        container_count=5,
        level_id="level_08",
        item_selection_strategy="prefix",
    )

    assert manifest["data_identity"] == config["data_identity"]
    assert manifest["selected_item_ids"] == [f"I{value:04d}" for value in range(20)]
    persisted = json.loads((tmp_path / "latest_manifest.json").read_text())
    assert persisted["data_identity"]["comparison_group_id"] == (
        "public_3dbppsi_cross_level_v1"
    )
