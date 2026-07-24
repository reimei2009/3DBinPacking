"""Level 5 load-capacity data contract."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

from ..schemas import Item


SYNTHETIC_PROFILE_ID = "synthetic_weight_factor_v1"


@dataclass(frozen=True)
class LoadCapacityOverride:
    item_id: str
    max_supported_weight_kg: float | None
    is_fragile: bool
    load_capacity_source: str


@dataclass(frozen=True)
class LoadBearingSettings:
    """Validated settings for the active Level 5 research profile."""

    weight_factor: float
    default_is_fragile: bool
    load_capacity_source: str
    overrides: tuple[LoadCapacityOverride, ...]

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "LoadBearingSettings":
        if config.get("contract_version") != 1:
            raise ValueError("Level 5 load-bearing contract_version must be 1")
        if config.get("level_id") != "level_05":
            raise ValueError("Level 5 load-bearing contract requires level_id='level_05'")
        profile = config.get("capacity_profile")
        if not isinstance(profile, dict):
            raise ValueError("Level 5 load-bearing contract requires capacity_profile")
        if profile.get("mode") != SYNTHETIC_PROFILE_ID:
            raise ValueError(
                f"Level 5 checkpoint only supports capacity_profile.mode='{SYNTHETIC_PROFILE_ID}'"
            )
        factor = _positive_number(profile.get("weight_factor"), "capacity_profile.weight_factor")
        default_fragile = _strict_bool(
            profile.get("default_is_fragile"), "capacity_profile.default_is_fragile"
        )
        source = _non_empty_text(
            profile.get("load_capacity_source"), "capacity_profile.load_capacity_source"
        )
        raw_overrides = profile.get("overrides", [])
        if not isinstance(raw_overrides, list):
            raise ValueError("capacity_profile.overrides must be a list")
        overrides: list[LoadCapacityOverride] = []
        seen: set[str] = set()
        for index, raw in enumerate(raw_overrides):
            field = f"capacity_profile.overrides[{index}]"
            if not isinstance(raw, dict):
                raise ValueError(f"{field} must be a mapping")
            item_id = _non_empty_text(raw.get("item_id"), f"{field}.item_id")
            if item_id in seen:
                raise ValueError(f"Duplicate Level 5 load-capacity override for item {item_id}")
            seen.add(item_id)
            fragile = _strict_bool(raw.get("is_fragile", default_fragile), f"{field}.is_fragile")
            capacity = (
                None
                if "max_supported_weight_kg" not in raw
                else _non_negative_number(
                    raw["max_supported_weight_kg"], f"{field}.max_supported_weight_kg"
                )
            )
            if fragile and capacity not in (None, 0.0):
                raise ValueError(
                    f"{field}: fragile items must have max_supported_weight_kg equal to 0"
                )
            if not fragile and capacity is not None and capacity <= 0:
                raise ValueError(
                    f"{field}: non-fragile items require max_supported_weight_kg > 0"
                )
            override_source = _non_empty_text(
                raw.get("load_capacity_source", f"{source}_override"),
                f"{field}.load_capacity_source",
            )
            overrides.append(
                LoadCapacityOverride(item_id, capacity, fragile, override_source)
            )
        return cls(factor, default_fragile, source, tuple(overrides))


@dataclass(frozen=True)
class LoadBearingAttributes:
    """Canonical per-item Level 5 strength attributes."""

    item_id: str
    max_supported_weight_kg: float
    is_fragile: bool
    load_capacity_source: str


def resolve_load_bearing_attributes(
    items: list[Item] | tuple[Item, ...],
    config: dict[str, Any],
) -> dict[str, LoadBearingAttributes]:
    """Resolve synthetic research attributes without mutating source items."""
    settings = LoadBearingSettings.from_config(config)
    item_by_id: dict[str, Item] = {}
    for item in items:
        item_id = item.item_id.strip()
        if not item_id:
            raise ValueError("Level 5 load-capacity input contains an empty item ID")
        if item_id in item_by_id:
            raise ValueError(f"Duplicate Level 5 load-capacity input item ID: {item_id}")
        if not isfinite(item.weight_kg) or item.weight_kg <= 0:
            raise ValueError(f"Item {item_id} requires a positive finite weight_kg")
        item_by_id[item_id] = item

    overrides = {value.item_id: value for value in settings.overrides}
    unknown = sorted(set(overrides) - set(item_by_id))
    if unknown:
        raise ValueError(f"Load-capacity overrides reference unknown items: {', '.join(unknown)}")

    resolved: dict[str, LoadBearingAttributes] = {}
    for item_id, item in item_by_id.items():
        override = overrides.get(item_id)
        fragile = settings.default_is_fragile if override is None else override.is_fragile
        if fragile:
            capacity = 0.0
        elif override is not None and override.max_supported_weight_kg is not None:
            capacity = override.max_supported_weight_kg
        else:
            capacity = settings.weight_factor * item.weight_kg
        source = settings.load_capacity_source if override is None else override.load_capacity_source
        resolved[item_id] = LoadBearingAttributes(item_id, capacity, fragile, source)
    return resolved


def _non_empty_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _strict_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def _positive_number(value: Any, field: str) -> float:
    number = _non_negative_number(value, field)
    if number <= 0:
        raise ValueError(f"{field} must be greater than 0")
    return number


def _non_negative_number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number") from exc
    if not isfinite(number) or number < 0:
        raise ValueError(f"{field} must be finite and non-negative")
    return number
