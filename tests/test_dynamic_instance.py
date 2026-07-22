import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from container_packing.instance_data import prepare_instance, select_item_rows


def test_item_and_container_counts_drive_names_notes_and_manifest(root: Path, tmp_path: Path):
    config = yaml.safe_load((root / "config/level_01/default.yaml").read_text(encoding="utf-8"))
    config["instance"]["item_count"] = 40
    config["instance"]["container_count"] = 2
    config["paths"]["raw_items_csv"] = str(root / "data/raw/dataset_small_items_original.csv")
    config["paths"]["processed_dir"] = str(tmp_path / "processed")
    config["paths"]["manifest_json"] = str(tmp_path / "processed/manifest.json")
    manifest = prepare_instance(tmp_path, config)
    items = list(pd.read_csv(tmp_path / manifest["items_csv"]).itertuples())
    containers = list(pd.read_csv(tmp_path / manifest["containers_csv"]).itertuples())

    assert len(items) == 40
    assert len(containers) == 2
    assert manifest["items_note"].startswith("First 40 rows")
    assert Path(manifest["items_csv"]).name == "items_40.csv"
    assert Path(manifest["containers_csv"]).name == "containers_2types.csv"
    assert manifest["instance_id"] == "level_01_40items_2containers"
    written = json.loads((tmp_path / "processed/manifest.json").read_text(encoding="utf-8"))
    assert written == manifest


def test_expands_synthetic_containers_and_uses_overrides(root: Path, tmp_path: Path):
    config = yaml.safe_load((root / "config/level_01/default.yaml").read_text(encoding="utf-8"))
    config["paths"]["raw_items_csv"] = str(root / "data/raw/dataset_small_items_original.csv")
    config["paths"]["processed_dir"] = "processed"
    config["paths"]["manifest_json"] = "processed/manifest.json"
    manifest = prepare_instance(tmp_path, config, item_count=3, container_count=7)
    containers = pd.read_csv(tmp_path / manifest["containers_csv"])
    assert manifest["instance_id"] == "level_01_3items_7containers"
    assert list(containers.container_id) == [f"C{i}" for i in range(1, 8)]
    assert containers.iloc[-1].length_mm > containers.iloc[4].length_mm


def test_seeded_item_selection_is_stable_audited_and_does_not_overwrite_prefix(root: Path, tmp_path: Path):
    config = yaml.safe_load((root / "config/level_01/default.yaml").read_text(encoding="utf-8"))
    config["paths"]["raw_items_csv"] = str(root / "data/raw/dataset_small_items_original.csv")
    config["paths"]["processed_dir"] = "processed"
    config["paths"]["manifest_json"] = "processed/latest.json"

    prefix = prepare_instance(tmp_path, config, item_count=20, container_count=5)
    first = prepare_instance(
        tmp_path, config, item_count=20, container_count=5,
        item_selection_strategy="stable_random", item_selection_seed=101,
    )
    second = prepare_instance(
        tmp_path, config, item_count=20, container_count=5,
        item_selection_strategy="stable_random", item_selection_seed=101,
    )
    different = prepare_instance(
        tmp_path, config, item_count=20, container_count=5,
        item_selection_strategy="stable_random", item_selection_seed=202,
    )

    assert Path(prefix["items_csv"]).name == "items_20.csv"
    assert Path(first["items_csv"]).name == "items_20__stable_random_seed101.csv"
    assert first["selected_item_ids"] == second["selected_item_ids"]
    assert first["selected_item_ids_checksum"] == second["selected_item_ids_checksum"]
    assert first["selected_item_ids_checksum"] != different["selected_item_ids_checksum"]
    assert first["item_selection_strategy"] == "stable_random"
    assert first["item_selection_seed"] == 101
    assert first["raw_items_checksum"]
    assert first["item_profile"]["unique_dimension_triples"] >= 1
    assert (tmp_path / prefix["items_csv"]).is_file()
    assert (tmp_path / first["items_csv"]).is_file()


def test_profile_selection_policies_match_their_data_meaning(root: Path):
    source = pd.read_csv(root / "data/raw/dataset_small_items_original.csv")
    source_volume = source.length * source.width * source.height

    largest = select_item_rows(source, 10, strategy="largest_volume")
    heaviest = select_item_rows(source, 10, strategy="heaviest")
    diverse = select_item_rows(source, 10, strategy="volume_stratified")
    largest_volume = largest.length * largest.width * largest.height
    diverse_volume = diverse.length * diverse.width * diverse.height

    assert largest_volume.min() >= source_volume.nlargest(10).min()
    assert heaviest.weight.min() >= source.weight.nlargest(10).min()
    assert diverse_volume.min() == source_volume.min()
    assert diverse_volume.max() == source_volume.max()


def test_stable_random_requires_an_explicit_selection_seed(root: Path):
    source = pd.read_csv(root / "data/raw/dataset_small_items_original.csv")
    with pytest.raises(ValueError, match="requires a non-negative selection seed"):
        select_item_rows(source, 10, strategy="stable_random")
