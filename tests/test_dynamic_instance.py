import json
from pathlib import Path

import pandas as pd
import yaml

from container_packing.instance_data import prepare_instance


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
