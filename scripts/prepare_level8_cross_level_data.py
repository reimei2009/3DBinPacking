"""Build the tracked Level 8 cross-level comparison inputs.

The source 3DBPPsi CSV is never modified.  This script preserves its complete
row order and physical attributes, then declares only Level 8 delivery fields.
"""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from container_packing.data_loader import load_config


ROOT = Path(__file__).resolve().parents[1]
SOURCE_ITEMS = ROOT / "data/raw/dataset_small_items_original.csv"
LEVEL1_CONFIG = ROOT / "config/level_01/default.yaml"
OUTPUT_DIR = ROOT / "data/raw/level_08/cross_level"
ITEMS_OUTPUT = OUTPUT_DIR / "dataset_small_delivery_items_v1.csv"
CONTAINERS_OUTPUT = OUTPUT_DIR / "container_catalog_c1_c10_v1.csv"
MANIFEST_OUTPUT = OUTPUT_DIR / "cross_level_comparison_v1_manifest.json"
DELIVERY_SOURCE = "cross_level_declared_delivery_v1"
CATALOG_ID = "cross_level_container_catalog_v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_items() -> int:
    with SOURCE_ITEMS.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        source_fields = list(reader.fieldnames or [])
    if not rows or "id_item" not in source_fields:
        raise ValueError(f"Invalid source item CSV: {SOURCE_ITEMS}")
    if len({row["id_item"] for row in rows}) != len(rows):
        raise ValueError("Source item IDs must be unique")

    fields = [
        *source_fields,
        "delivery_priority",
        "delivery_stop_id",
        "delivery_data_source",
    ]
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with ITEMS_OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index, row in enumerate(rows):
            priority = index % 5 + 1
            writer.writerow(
                {
                    **row,
                    "delivery_priority": priority,
                    "delivery_stop_id": f"STOP-{priority:03d}",
                    "delivery_data_source": DELIVERY_SOURCE,
                }
            )
    return len(rows)


def _container_rows(count: int = 10) -> list[dict[str, object]]:
    config = load_config(LEVEL1_CONFIG)
    rows = [dict(value) for value in config.get("containers", [])]
    if len(rows) != 5:
        raise ValueError("Level 1 must declare the canonical C1-C5 catalog")
    while len(rows) < count:
        previous = rows[-1]
        number = len(rows) + 1
        rows.append(
            {
                "container_id": f"C{number}",
                "length_mm": float(previous["length_mm"]) + 500,
                "width_mm": float(previous["width_mm"]) + 50,
                "height_mm": float(previous["height_mm"]) + 100,
                "max_weight_kg": float(previous["max_weight_kg"]) + 750,
                "cost": float(previous["cost"]) + 150,
                "availability": 1,
            }
        )
    return rows


def _write_containers() -> int:
    rows = _container_rows()
    fields = [
        "container_id",
        "length_mm",
        "width_mm",
        "height_mm",
        "max_weight_kg",
        "availability",
        "cost",
        "volume_m3",
        "container_catalog_id",
        "data_status",
        "design_note",
    ]
    with CONTAINERS_OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            length = float(row["length_mm"])
            width = float(row["width_mm"])
            height = float(row["height_mm"])
            writer.writerow(
                {
                    **row,
                    "volume_m3": length * width * height / 1_000_000_000,
                    "container_catalog_id": CATALOG_ID,
                    "data_status": "cross_level_comparable_synthetic_catalog",
                    "design_note": "Matches the canonical Level 1 catalog and deterministic extension rule",
                }
            )
    return len(rows)


def main() -> int:
    item_count = _write_items()
    container_count = _write_containers()
    manifest = {
        "schema_version": "1.0",
        "dataset_id": "public_3dbppsi_dataset_small_delivery_enriched_v1",
        "container_catalog_id": CATALOG_ID,
        "comparison_group_id": "public_3dbppsi_cross_level_v1",
        "transformation": "preserve source rows; add cyclic five-stop delivery declarations only",
        "delivery_priority_rule": "source_row_zero_based_modulo_5_plus_1",
        "source_items": str(SOURCE_ITEMS.relative_to(ROOT)).replace("\\", "/"),
        "source_items_sha256": _sha256(SOURCE_ITEMS),
        "items_file": str(ITEMS_OUTPUT.relative_to(ROOT)).replace("\\", "/"),
        "items_sha256": _sha256(ITEMS_OUTPUT),
        "item_count": item_count,
        "containers_file": str(CONTAINERS_OUTPUT.relative_to(ROOT)).replace("\\", "/"),
        "containers_sha256": _sha256(CONTAINERS_OUTPUT),
        "container_count": container_count,
    }
    MANIFEST_OUTPUT.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
