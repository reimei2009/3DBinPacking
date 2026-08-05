"""Cấu hình có kiểu cho tìm kiếm container trên toàn inventory."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

from .inventory import InventorySearchLimits


@dataclass(frozen=True)
class ContainerSearchConfiguration:
    """Cấu hình promotion an toàn của inventory-aware subset search."""

    enabled: bool
    limits: InventorySearchLimits
    exhaustive_max_containers: int = 10
    max_candidates_per_count: int = 32
    neighborhood_width: int = 8
    soft_volume_buffer_ratio: float = 0.10
    time_limit_seconds: float | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any] | None) -> "ContainerSearchConfiguration":
        raw = dict(value or {})
        enabled = _strict_bool(raw.get("enabled", False), "enabled")
        initial = _positive_int(
            raw.get("initial_used_container_count", 1),
            "initial_used_container_count",
        )
        maximum = _positive_int(
            raw.get("max_used_container_count", initial),
            "max_used_container_count",
        )
        automatically_increase = _strict_bool(
            raw.get("automatically_increase_container_count", False),
            "automatically_increase_container_count",
        )
        exhaustive = _positive_int(
            raw.get("exhaustive_max_containers", 10),
            "exhaustive_max_containers",
        )
        candidate_limit = _positive_int(
            raw.get("max_candidates_per_count", 32),
            "max_candidates_per_count",
        )
        neighborhood_width = _positive_int(
            raw.get("neighborhood_width", 8),
            "neighborhood_width",
        )
        soft_buffer = _finite_float(
            raw.get("soft_volume_buffer_ratio", 0.10),
            "soft_volume_buffer_ratio",
        )
        if not 0 <= soft_buffer <= 1:
            raise ValueError("container_search.soft_volume_buffer_ratio must be in [0, 1]")
        raw_time_limit = raw.get("time_limit_seconds")
        time_limit = None
        if raw_time_limit is not None:
            time_limit = _finite_float(raw_time_limit, "time_limit_seconds")
            if time_limit <= 0:
                raise ValueError("container_search.time_limit_seconds must be positive")
        return cls(
            enabled=enabled,
            limits=InventorySearchLimits(initial, maximum, automatically_increase),
            exhaustive_max_containers=exhaustive,
            max_candidates_per_count=candidate_limit,
            neighborhood_width=neighborhood_width,
            soft_volume_buffer_ratio=soft_buffer,
            time_limit_seconds=time_limit,
        )

    def metadata(self) -> dict[str, object]:
        return {
            "container_search_enabled": self.enabled,
            "initial_used_container_count": self.limits.initial_used_container_count,
            "max_used_container_count": self.limits.max_used_container_count,
            "automatically_increase_container_count": (
                self.limits.automatically_increase_container_count
            ),
            "container_search_time_limit_seconds": self.time_limit_seconds,
        }


def _positive_int(value: object, name: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"container_search.{name} must be a positive integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"container_search.{name} must be a positive integer"
        ) from exc
    if parsed <= 0 or parsed != value:
        raise ValueError(f"container_search.{name} must be a positive integer")
    return parsed


def _finite_float(value: object, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"container_search.{name} must be a finite number")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"container_search.{name} must be a finite number") from exc
    if not isfinite(parsed):
        raise ValueError(f"container_search.{name} must be a finite number")
    return parsed


def _strict_bool(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"container_search.{name} must be true or false")
    return value
