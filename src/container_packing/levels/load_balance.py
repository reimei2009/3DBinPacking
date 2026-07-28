"""Level 7 container center-of-mass and balance data contract."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

from ..schemas import Container


SYMMETRIC_CENTER_BAND_PROFILE_ID = "symmetric_center_band_v1"


@dataclass(frozen=True)
class ContainerBalanceOverride:
    """Optional profile replacement for one physical container instance."""

    container_id: str
    target_longitudinal_ratio: float | None
    target_lateral_ratio: float | None
    max_longitudinal_offset_ratio: float | None
    max_lateral_offset_ratio: float | None
    balance_profile_source: str | None


@dataclass(frozen=True)
class ContainerBalanceSettings:
    """Validated inactive Level 7 balance profile.

    The profile is intentionally independent of payload capacity and does not
    activate a Level 7 runtime. It only locks future COG semantics.
    """

    target_longitudinal_ratio: float
    target_lateral_ratio: float
    max_longitudinal_offset_ratio: float
    max_lateral_offset_ratio: float
    balance_profile_source: str
    overrides: tuple[ContainerBalanceOverride, ...]

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "ContainerBalanceSettings":
        if config.get("contract_version") != 1:
            raise ValueError("Level 7 balance contract_version must be 1")
        if config.get("level_id") != "level_07":
            raise ValueError("Level 7 balance contract requires level_id='level_07'")
        if config.get("status") != "data_contract_only":
            raise ValueError("Level 7 balance contract must remain data_contract_only")
        profile = config.get("balance_profile")
        if not isinstance(profile, dict):
            raise ValueError("Level 7 balance contract requires balance_profile")
        if profile.get("mode") != SYMMETRIC_CENTER_BAND_PROFILE_ID:
            raise ValueError(
                "Level 7 checkpoint only supports "
                f"balance_profile.mode='{SYMMETRIC_CENTER_BAND_PROFILE_ID}'"
            )

        defaults = _profile_values(profile, "balance_profile", allow_missing=False)
        raw_overrides = profile.get("overrides", [])
        if not isinstance(raw_overrides, list):
            raise ValueError("balance_profile.overrides must be a list")
        overrides: list[ContainerBalanceOverride] = []
        seen: set[str] = set()
        for index, raw in enumerate(raw_overrides):
            field = f"balance_profile.overrides[{index}]"
            if not isinstance(raw, dict):
                raise ValueError(f"{field} must be a mapping")
            container_id = _non_empty_text(raw.get("container_id"), f"{field}.container_id")
            if container_id in seen:
                raise ValueError(
                    f"Duplicate Level 7 balance-profile override for container {container_id}"
                )
            seen.add(container_id)
            values = _profile_values(raw, field, allow_missing=True)
            overrides.append(ContainerBalanceOverride(container_id, *values))
        return cls(*defaults, tuple(overrides))


@dataclass(frozen=True)
class ContainerBalanceAttributes:
    """Resolved future COG target and tolerance for one container."""

    container_id: str
    target_longitudinal_ratio: float
    target_lateral_ratio: float
    max_longitudinal_offset_ratio: float
    max_lateral_offset_ratio: float
    balance_profile_source: str


def resolve_container_balance_attributes(
    containers: list[Container] | tuple[Container, ...],
    config: dict[str, Any],
) -> dict[str, ContainerBalanceAttributes]:
    """Resolve Level 7 profile values without mutating containers or inputs."""
    settings = ContainerBalanceSettings.from_config(config)
    container_by_id: dict[str, Container] = {}
    for container in containers:
        container_id = container.container_id.strip()
        if not container_id:
            raise ValueError("Level 7 balance input contains an empty container ID")
        if container_id in container_by_id:
            raise ValueError(
                f"Duplicate Level 7 balance input container ID: {container_id}"
            )
        if not isfinite(container.length_mm) or container.length_mm <= 0:
            raise ValueError(f"Container {container_id} requires a positive finite length_mm")
        if not isfinite(container.width_mm) or container.width_mm <= 0:
            raise ValueError(f"Container {container_id} requires a positive finite width_mm")
        container_by_id[container_id] = container

    overrides = {value.container_id: value for value in settings.overrides}
    unknown = sorted(set(overrides) - set(container_by_id))
    if unknown:
        raise ValueError(
            "Balance-profile overrides reference unknown containers: " + ", ".join(unknown)
        )

    resolved: dict[str, ContainerBalanceAttributes] = {}
    for container_id in container_by_id:
        override = overrides.get(container_id)
        resolved[container_id] = ContainerBalanceAttributes(
            container_id=container_id,
            target_longitudinal_ratio=(
                settings.target_longitudinal_ratio
                if override is None or override.target_longitudinal_ratio is None
                else override.target_longitudinal_ratio
            ),
            target_lateral_ratio=(
                settings.target_lateral_ratio
                if override is None or override.target_lateral_ratio is None
                else override.target_lateral_ratio
            ),
            max_longitudinal_offset_ratio=(
                settings.max_longitudinal_offset_ratio
                if override is None or override.max_longitudinal_offset_ratio is None
                else override.max_longitudinal_offset_ratio
            ),
            max_lateral_offset_ratio=(
                settings.max_lateral_offset_ratio
                if override is None or override.max_lateral_offset_ratio is None
                else override.max_lateral_offset_ratio
            ),
            balance_profile_source=(
                settings.balance_profile_source
                if override is None or override.balance_profile_source is None
                else override.balance_profile_source
            ),
        )
    return resolved


def _profile_values(
    value: dict[str, Any], field: str, *, allow_missing: bool
) -> tuple[float | None, float | None, float | None, float | None, str | None]:
    target_longitudinal = _optional_ratio(
        value, "target_longitudinal_ratio", field, upper=1.0, allow_missing=allow_missing
    )
    target_lateral = _optional_ratio(
        value, "target_lateral_ratio", field, upper=1.0, allow_missing=allow_missing
    )
    max_longitudinal = _optional_ratio(
        value, "max_longitudinal_offset_ratio", field, upper=0.5, allow_missing=allow_missing
    )
    max_lateral = _optional_ratio(
        value, "max_lateral_offset_ratio", field, upper=0.5, allow_missing=allow_missing
    )
    source = _optional_text(value, "balance_profile_source", field, allow_missing=allow_missing)
    return target_longitudinal, target_lateral, max_longitudinal, max_lateral, source


def _optional_ratio(
    values: dict[str, Any], key: str, field: str, *, upper: float, allow_missing: bool
) -> float | None:
    if key not in values:
        if allow_missing:
            return None
        raise ValueError(f"{field}.{key} must be a number")
    value = values[key]
    if isinstance(value, bool):
        raise ValueError(f"{field}.{key} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field}.{key} must be a number") from exc
    if not isfinite(number) or not 0.0 <= number <= upper:
        raise ValueError(f"{field}.{key} must be finite and between 0 and {upper}")
    return number


def _optional_text(
    values: dict[str, Any], key: str, field: str, *, allow_missing: bool
) -> str | None:
    if key not in values:
        if allow_missing:
            return None
        raise ValueError(f"{field}.{key} must be a non-empty string")
    return _non_empty_text(values[key], f"{field}.{key}")


def _non_empty_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()
