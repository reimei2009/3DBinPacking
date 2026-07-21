"""Reproducible, dynamically named Level 1 instance preparation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

SOURCE_URL = "https://github.com/MRVSmartNetworks/container_loading_heuristics/tree/main/data/dataset_small"


def resolve_count(value: int | None, fallback: Any, label: str) -> int:
    """Resolve and validate a positive instance-size parameter."""
    count = int(fallback if value is None else value)
    if count <= 0:
        raise ValueError(f"{label} must be a positive integer, got {count}")
    return count


def instance_id(item_count: int, container_count: int, level_id: str = "level_01") -> str:
    return f"{level_id}_{item_count}items_{container_count}containers"


def _path(root: Path, value: str | Path) -> Path:
    candidate = Path(value)
    return candidate if candidate.is_absolute() else root / candidate


def _portable_path(root: Path, value: Path) -> str:
    try:
        return value.relative_to(root).as_posix()
    except ValueError:
        return str(value.resolve())


def _container_definitions(config: dict[str, Any], requested: int) -> list[dict[str, Any]]:
    """Select configured containers and deterministically extend synthetic ones if needed."""
    configured = [dict(value) for value in config.get("containers", [])]
    if not configured:
        raise ValueError("Config must define at least one base container")
    selected = configured[:requested]
    while len(selected) < requested:
        previous = selected[-1]
        number = len(selected) + 1
        selected.append({
            "container_id": f"C{number}",
            "length_mm": float(previous["length_mm"]) + 500,
            "width_mm": float(previous["width_mm"]) + 50,
            "height_mm": float(previous["height_mm"]) + 100,
            "max_weight_kg": float(previous["max_weight_kg"]) + 750,
            "cost": float(previous["cost"]) + 150,
            "availability": 1,
            "design_note": "Deterministically extended synthetic Level 1 container",
        })
    return selected


def prepare_instance(
    root: Path,
    config: dict[str, Any],
    *,
    item_count: int | None = None,
    container_count: int | None = None,
    level_id: str = "level_01",
) -> dict[str, Any]:
    """Prepare one requested instance and return its manifest.

    File names, notes, manifest values, and later output names are derived from
    the actual row counts; callers never need to synchronize them manually.
    """
    settings = config.get("instance", {})
    if "item_count" not in settings or "container_count" not in settings:
        raise ValueError("Config instance must define item_count and container_count")
    requested_items = resolve_count(item_count, settings["item_count"], "item_count")
    requested_containers = resolve_count(container_count, settings["container_count"], "container_count")
    paths = config["paths"]
    raw_path = _path(root, paths["raw_items_csv"])
    if not raw_path.exists():
        raise FileNotFoundError(f"Missing raw benchmark file: {raw_path}")
    source = pd.read_csv(raw_path, encoding="utf-8-sig")
    required = {
        "id_item", "length", "width", "height", "weight", "nesting_height",
        "stackability_code", "forced_orientation", "max_stackability",
    }
    missing = required - set(source.columns)
    if missing:
        raise ValueError(f"Raw items file is missing columns: {sorted(missing)}")
    if requested_items > len(source):
        raise ValueError(f"Requested {requested_items} items but raw data contains only {len(source)} rows")

    items = source.head(requested_items).copy()
    actual_items = len(items)
    items.insert(0, "level1_order", range(1, actual_items + 1))
    items = items.rename(columns={
        "length": "length_mm", "width": "width_mm", "height": "height_mm",
        "weight": "weight_kg", "nesting_height": "nesting_height_mm",
    })
    items["used_in_level1"] = 1
    items["level1_note"] = (
        f"First {actual_items} rows of public dataset_small; advanced fields ignored in Level 1"
    )
    items["source_url"] = SOURCE_URL

    rows = []
    for definition in _container_definitions(config, requested_containers):
        length = float(definition["length_mm"])
        width = float(definition["width_mm"])
        height = float(definition["height_mm"])
        rows.append({
            "container_id": str(definition["container_id"]),
            "length_mm": length, "width_mm": width, "height_mm": height,
            "max_weight_kg": float(definition["max_weight_kg"]),
            "availability": int(definition.get("availability", 1)),
            "cost": float(definition["cost"]),
            "volume_m3": length * width * height / 1_000_000_000,
            "data_status": "synthetic_level1",
            "unit_note": "mm, kg; cost is a synthetic comparison score",
            "design_note": definition.get(
                "design_note", "Synthetic heterogeneous container defined by Level 1 configuration"
            ),
        })
    containers = pd.DataFrame(rows)
    actual_containers = len(containers)
    run_id = instance_id(actual_items, actual_containers, level_id)

    processed = _path(root, paths["processed_dir"])
    processed.mkdir(parents=True, exist_ok=True)
    items_path = processed / f"items_{actual_items}.csv"
    containers_path = processed / f"containers_{actual_containers}types.csv"
    items.to_csv(items_path, index=False, encoding="utf-8-sig")
    containers.to_csv(containers_path, index=False, encoding="utf-8-sig")
    manifest = {
        "instance_id": run_id,
        "level_id": level_id,
        "n_items": actual_items,
        "n_containers": actual_containers,
        "items_csv": _portable_path(root, items_path),
        "containers_csv": _portable_path(root, containers_path),
        "source_url": SOURCE_URL,
        "items_note": items["level1_note"].iloc[0],
    }
    latest_manifest = _path(root, paths.get("manifest_json", "data/processed/level1_manifest.json"))
    manifests_dir = processed / "manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest, indent=2, ensure_ascii=False)
    latest_manifest.write_text(payload, encoding="utf-8")
    (manifests_dir / f"{run_id}.json").write_text(payload, encoding="utf-8")
    return manifest
