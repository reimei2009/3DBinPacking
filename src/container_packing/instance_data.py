"""Reproducible, dynamically named Level 1 instance preparation."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Any

import pandas as pd

from .provenance import sha256_file

SOURCE_URL = "https://github.com/MRVSmartNetworks/container_loading_heuristics/tree/main/data/dataset_small"
ITEM_SELECTION_STRATEGIES = (
    "prefix",
    "stable_random",
    "volume_stratified",
    "largest_volume",
    "heaviest",
)


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


def _selection_checksum(item_ids: list[str]) -> str:
    payload = json.dumps(item_ids, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def select_item_rows(
    source: pd.DataFrame,
    item_count: int,
    *,
    strategy: str = "prefix",
    seed: int | None = None,
) -> pd.DataFrame:
    """Select an immutable ordered subset using a documented deterministic policy."""
    if strategy not in ITEM_SELECTION_STRATEGIES:
        raise ValueError(
            f"Unsupported item selection strategy {strategy!r}; expected one of {', '.join(ITEM_SELECTION_STRATEGIES)}"
        )
    required = {"id_item"}
    if strategy in {"volume_stratified", "largest_volume"}:
        required.update({"length", "width", "height"})
    if strategy == "heaviest":
        required.add("weight")
    missing = sorted(required - set(source.columns))
    if missing:
        raise ValueError(f"Item selection {strategy!r} requires raw columns: {', '.join(missing)}")
    if item_count <= 0 or item_count > len(source):
        raise ValueError(f"item_count must be between 1 and {len(source)}, got {item_count}")
    indexed = source.reset_index(drop=False).rename(columns={"index": "_source_row"}).copy()
    if strategy == "prefix":
        selected = indexed.head(item_count)
    elif strategy == "stable_random":
        if seed is None or int(seed) < 0:
            raise ValueError("stable_random item selection requires a non-negative selection seed")
        selected = indexed.assign(_selection_rank=indexed.apply(
            lambda row: hashlib.sha256(
                f"{int(seed)}:{int(row['_source_row'])}:{row['id_item']}".encode("utf-8")
            ).hexdigest(),
            axis=1,
        )).sort_values(["_selection_rank", "_source_row"]).head(item_count)
    else:
        indexed["_volume_mm3"] = (
            pd.to_numeric(indexed["length"])
            * pd.to_numeric(indexed["width"])
            * pd.to_numeric(indexed["height"])
        )
        indexed["_weight_kg"] = pd.to_numeric(indexed["weight"])
        if strategy == "largest_volume":
            selected = indexed.sort_values(
                ["_volume_mm3", "id_item", "_source_row"], ascending=[False, True, True]
            ).head(item_count)
        elif strategy == "heaviest":
            selected = indexed.sort_values(
                ["_weight_kg", "id_item", "_source_row"], ascending=[False, True, True]
            ).head(item_count)
        else:
            ranked = indexed.sort_values(["_volume_mm3", "id_item", "_source_row"]).reset_index(drop=True)
            if item_count == 1:
                positions = [(len(ranked) - 1) // 2]
            else:
                positions = [round(index * (len(ranked) - 1) / (item_count - 1)) for index in range(item_count)]
            selected = ranked.iloc[positions]
    return selected.sort_values("_source_row").drop(
        columns=["_source_row", "_selection_rank", "_volume_mm3", "_weight_kg"], errors="ignore"
    ).reset_index(drop=True)


def item_selection_fingerprint(
    source_path: Path,
    item_count: int,
    *,
    strategy: str = "prefix",
    seed: int | None = None,
) -> dict[str, Any]:
    """Return the exact deterministic item identity used by benchmark comparison."""
    source = pd.read_csv(source_path, encoding="utf-8-sig")
    selected = select_item_rows(source, item_count, strategy=strategy, seed=seed)
    item_ids = selected["id_item"].astype(str).tolist()
    return {
        "raw_items_checksum": sha256_file(source_path),
        "selected_item_ids": item_ids,
        "selected_item_ids_checksum": _selection_checksum(item_ids),
        "selection_strategy": strategy,
        "selection_seed": seed,
    }


def _item_profile(items: pd.DataFrame) -> dict[str, Any]:
    volume = items["length_mm"] * items["width_mm"] * items["height_mm"]
    return {
        "total_volume_mm3": float(volume.sum()),
        "volume_mm3_min": float(volume.min()),
        "volume_mm3_mean": float(volume.mean()),
        "volume_mm3_max": float(volume.max()),
        "weight_kg_min": float(items["weight_kg"].min()),
        "weight_kg_mean": float(items["weight_kg"].mean()),
        "weight_kg_max": float(items["weight_kg"].max()),
        "unique_dimension_triples": int(items[["length_mm", "width_mm", "height_mm"]].drop_duplicates().shape[0]),
    }


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
    item_selection_strategy: str | None = None,
    item_selection_seed: int | None = None,
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

    strategy = str(item_selection_strategy or settings.get("item_selection_strategy", "prefix"))
    configured_selection_seed = settings.get("item_selection_seed")
    selection_seed = configured_selection_seed if item_selection_seed is None else item_selection_seed
    selection_seed = None if selection_seed is None else int(selection_seed)
    items = select_item_rows(source, requested_items, strategy=strategy, seed=selection_seed)
    actual_items = len(items)
    items.insert(0, "level1_order", range(1, actual_items + 1))
    items = items.rename(columns={
        "length": "length_mm", "width": "width_mm", "height": "height_mm",
        "weight": "weight_kg", "nesting_height": "nesting_height_mm",
    })
    items["used_in_level1"] = 1
    selection_notes = {
        "prefix": f"First {actual_items} rows of public dataset_small",
        "stable_random": f"Stable hash sample of {actual_items} rows using selection seed {selection_seed}",
        "volume_stratified": f"{actual_items} rows distributed across the public dataset_small volume range",
        "largest_volume": f"{actual_items} largest-volume rows of public dataset_small",
        "heaviest": f"{actual_items} heaviest rows of public dataset_small",
    }
    items["level1_note"] = f"{selection_notes[strategy]}; advanced fields ignored in Level 1"
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
    selection_token = strategy if selection_seed is None else f"{strategy}_seed{selection_seed}"
    run_id = instance_id(actual_items, actual_containers, level_id)
    if strategy != "prefix":
        run_id = f"{run_id}__{selection_token}"

    processed = _path(root, paths["processed_dir"])
    processed.mkdir(parents=True, exist_ok=True)
    items_suffix = "" if strategy == "prefix" else f"__{selection_token}"
    items_path = processed / f"items_{actual_items}{items_suffix}.csv"
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
        "raw_items_checksum": sha256_file(raw_path),
        "item_selection_strategy": strategy,
        "item_selection_seed": selection_seed,
        "selected_item_ids": items["id_item"].astype(str).tolist(),
        "selected_item_ids_checksum": _selection_checksum(items["id_item"].astype(str).tolist()),
        "item_profile": _item_profile(items),
    }
    latest_manifest = _path(root, paths.get("manifest_json", "data/processed/level1_manifest.json"))
    manifests_dir = processed / "manifests"
    manifests_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(manifest, indent=2, ensure_ascii=False)
    latest_manifest.write_text(payload, encoding="utf-8")
    (manifests_dir / f"{run_id}.json").write_text(payload, encoding="utf-8")
    return manifest
