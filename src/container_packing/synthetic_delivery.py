"""Deterministic synthetic Level 8 delivery-data generation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from random import Random
from typing import Any

import pandas as pd

from .data_loader import load_config
from .provenance import sha256_file
from .runtime.project import find_project_root


@dataclass(frozen=True)
class SyntheticDeliveryProfile:
    profile_id: str
    seed: int
    item_count: int
    container_count: int
    output_dir: Path
    item_file_name: str
    container_file_name: str
    delivery_stop_count: int
    length_range: tuple[int, int]
    width_range: tuple[int, int]
    height_range: tuple[int, int]
    weight_range: tuple[int, int]
    container_template: dict[str, float]


def load_synthetic_delivery_profile(path: str | Path, *, root: Path | None = None) -> SyntheticDeliveryProfile:
    root = root or find_project_root(__file__)
    config_path = Path(path)
    if not config_path.is_absolute():
        config_path = root / config_path
    config = load_config(config_path)
    profile_id = _text(config.get("profile_id"), "profile_id")
    seed = _positive_int(config.get("seed"), "seed", allow_zero=True)
    item_count = _positive_int(config.get("item_count"), "item_count")
    container_count = _positive_int(config.get("container_count"), "container_count")
    stop_count = _positive_int(config.get("delivery_stop_count"), "delivery_stop_count")
    if stop_count > item_count:
        raise ValueError("delivery_stop_count must not exceed item_count")
    output_dir = Path(_text(config.get("output_dir"), "output_dir"))
    if not output_dir.is_absolute():
        output_dir = root / output_dir
    template = config.get("container_template")
    if not isinstance(template, dict):
        raise ValueError("container_template must be a mapping")
    resolved_template = {name: float(template[name]) for name in (
        "length_mm", "width_mm", "height_mm", "max_weight_kg", "cost"
    )}
    if any(value <= 0 for value in resolved_template.values()):
        raise ValueError("container_template values must be positive")
    dimensions = config.get("dimensions_mm")
    if not isinstance(dimensions, dict):
        raise ValueError("dimensions_mm must be a mapping")
    return SyntheticDeliveryProfile(
        profile_id=profile_id, seed=seed, item_count=item_count, container_count=container_count,
        output_dir=output_dir,
        item_file_name=_file_name(config.get("item_file_name"), "item_file_name"),
        container_file_name=_file_name(config.get("container_file_name"), "container_file_name"),
        delivery_stop_count=stop_count,
        length_range=_range(dimensions.get("length"), "dimensions_mm.length"),
        width_range=_range(dimensions.get("width"), "dimensions_mm.width"),
        height_range=_range(dimensions.get("height"), "dimensions_mm.height"),
        weight_range=_range(config.get("weight_kg"), "weight_kg"),
        container_template=resolved_template,
    )


def generate_synthetic_delivery_data(profile: SyntheticDeliveryProfile, *, overwrite: bool = False) -> dict[str, Any]:
    """Write deterministic source CSVs and a provenance manifest for one profile."""
    output_dir = profile.output_dir
    item_path = output_dir / profile.item_file_name
    container_path = output_dir / profile.container_file_name
    manifest_path = output_dir / f"{profile.profile_id}_manifest.json"
    existing = [str(path) for path in (item_path, container_path, manifest_path) if path.exists()]
    if existing and not overwrite:
        raise FileExistsError(
            "Refusing to overwrite generated Level 8 synthetic data; use --overwrite explicitly: " + ", ".join(existing)
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    random = Random(profile.seed)
    items = pd.DataFrame(_item_rows(profile, random))
    containers = pd.DataFrame(_container_rows(profile))
    _atomic_csv(items, item_path)
    _atomic_csv(containers, container_path)
    manifest = {
        "generator_id": "synthetic_level_08_delivery_v1",
        "profile_id": profile.profile_id,
        "seed": profile.seed,
        "item_count": profile.item_count,
        "container_count": profile.container_count,
        "delivery_stop_count": profile.delivery_stop_count,
        "priority_convention": "ascending_is_earlier_delivery",
        "item_csv": item_path.name,
        "container_csv": container_path.name,
        "item_csv_sha256": sha256_file(item_path),
        "container_csv_sha256": sha256_file(container_path),
        "profile_fingerprint": _profile_fingerprint(profile),
    }
    _atomic_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", manifest_path)
    return {**manifest, "manifest_path": str(manifest_path), "item_path": str(item_path), "container_path": str(container_path)}


def _item_rows(profile: SyntheticDeliveryProfile, random: Random) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index in range(1, profile.item_count + 1):
        priority = 1 + ((index - 1) % profile.delivery_stop_count)
        rows.append({
            "shipment_unit_id": f"L8-{index:06d}",
            "outer_length_mm": random.randint(*profile.length_range),
            "outer_width_mm": random.randint(*profile.width_range),
            "outer_height_mm": random.randint(*profile.height_range),
            "gross_mass_kg": round(random.uniform(*profile.weight_range), 3),
            "delivery_sequence": priority,
            "route_stop": f"STOP-{priority:03d}",
            "delivery_metadata_source": "synthetic_level_08_generator_v1",
            "synthetic_profile_id": profile.profile_id,
        })
    return rows


def _container_rows(profile: SyntheticDeliveryProfile) -> list[dict[str, Any]]:
    base = profile.container_template
    rows: list[dict[str, Any]] = []
    for index in range(1, profile.container_count + 1):
        factor = 1.0 + 0.04 * ((index - 1) % 5)
        length = round(base["length_mm"] * factor, 3)
        width = round(base["width_mm"] * (1.0 + 0.02 * ((index - 1) % 3)), 3)
        height = round(base["height_mm"] * (1.0 + 0.03 * ((index - 1) % 4)), 3)
        rows.append({
            "container_id": f"L8C{index:03d}", "length_mm": length, "width_mm": width, "height_mm": height,
            "max_weight_kg": round(base["max_weight_kg"] * factor, 3), "availability": 1,
            "cost": round(base["cost"] * factor, 3), "volume_m3": length * width * height / 1_000_000_000,
            "data_status": "synthetic_level_08_generator_v1",
            "design_note": "Deterministic synthetic Level 8 container; not carrier data",
        })
    return rows


def _profile_fingerprint(profile: SyntheticDeliveryProfile) -> str:
    payload = {key: getattr(profile, key) for key in (
        "profile_id", "seed", "item_count", "container_count", "delivery_stop_count",
        "length_range", "width_range", "height_range", "weight_range", "container_template",
    )}
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False, encoding="utf-8-sig")
    temporary.replace(path)


def _atomic_text(text: str, path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _file_name(value: Any, field: str) -> str:
    name = _text(value, field)
    if Path(name).name != name or not name.endswith(".csv"):
        raise ValueError(f"{field} must be a CSV file name without a directory")
    return name


def _positive_int(value: Any, field: str, *, allow_zero: bool = False) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if result < 0 or (not allow_zero and result <= 0):
        raise ValueError(f"{field} must be {'non-negative' if allow_zero else 'positive'}")
    return result


def _range(value: Any, field: str) -> tuple[int, int]:
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError(f"{field} must be a two-value list")
    lower = _positive_int(value[0], f"{field}[0]")
    upper = _positive_int(value[1], f"{field}[1]")
    if lower > upper:
        raise ValueError(f"{field} lower bound must not exceed upper bound")
    return lower, upper
