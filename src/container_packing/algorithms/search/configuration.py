"""Cấu hình có kiểu cho tìm kiếm container trên toàn inventory."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

from .inventory import InventorySearchLimits


@dataclass(frozen=True)
class AdaptiveClusterEliminationConfiguration:
    """Portfolio destroy/repack dựa trên failed item và destination cluster."""

    enabled: bool = False
    maximum_destination_containers: int = 3
    neighborhood_sizes: tuple[int, ...] = (4, 8, 16, 24)
    beam_width: int = 8
    maximum_candidates: int = 256
    maximum_target_containers: int = 8
    minimum_validation_reserve_seconds: float = 2.0

    @classmethod
    def from_mapping(
        cls, value: dict[str, Any] | None,
    ) -> "AdaptiveClusterEliminationConfiguration":
        raw = dict(value or {})
        enabled = _strict_bool(
            raw.get("enabled", False), "adaptive_cluster_elimination.enabled",
        )
        maximum_destinations = _positive_int(
            raw.get("maximum_destination_containers", 3),
            "adaptive_cluster_elimination.maximum_destination_containers",
        )
        sizes_raw = raw.get("neighborhood_sizes", [4, 8, 16, 24])
        if not isinstance(sizes_raw, list | tuple) or not sizes_raw:
            raise ValueError(
                "container_search.consolidation.container_elimination."
                "adaptive_cluster_elimination.neighborhood_sizes must be non-empty"
            )
        sizes = tuple(
            _positive_int(value, "adaptive_cluster_elimination.neighborhood_sizes")
            for value in sizes_raw
        )
        if tuple(sorted(set(sizes))) != sizes:
            raise ValueError(
                "adaptive_cluster_elimination.neighborhood_sizes must be "
                "strictly increasing and contain no duplicates"
            )
        beam_width = _positive_int(
            raw.get("beam_width", 8), "adaptive_cluster_elimination.beam_width",
        )
        maximum_candidates = _positive_int(
            raw.get("maximum_candidates", 256),
            "adaptive_cluster_elimination.maximum_candidates",
        )
        maximum_targets = _positive_int(
            raw.get("maximum_target_containers", 8),
            "adaptive_cluster_elimination.maximum_target_containers",
        )
        validation_reserve = _non_negative_float(
            raw.get("minimum_validation_reserve_seconds", 2.0),
            "adaptive_cluster_elimination.minimum_validation_reserve_seconds",
        )
        return cls(
            enabled, maximum_destinations, sizes, beam_width,
            maximum_candidates, maximum_targets, validation_reserve,
        )

    def metadata(self) -> dict[str, object]:
        return {
            "adaptive_cluster_elimination_enabled": self.enabled,
            "adaptive_cluster_maximum_destination_containers": (
                self.maximum_destination_containers
            ),
            "adaptive_cluster_neighborhood_sizes": list(self.neighborhood_sizes),
            "adaptive_cluster_beam_width": self.beam_width,
            "adaptive_cluster_maximum_candidates": self.maximum_candidates,
            "adaptive_cluster_maximum_target_containers": (
                self.maximum_target_containers
            ),
            "adaptive_cluster_minimum_validation_reserve_seconds": (
                self.minimum_validation_reserve_seconds
            ),
        }


@dataclass(frozen=True)
class ContainerEliminationConfiguration:
    """Giới hạn cho relocation và partial repack nhằm đóng container."""

    enabled: bool = False
    maximum_target_containers: int = 8
    maximum_candidates: int = 1024
    phase_time_fractions: tuple[float, float, float] = (0.35, 0.25, 0.40)
    adaptive_cluster_elimination: AdaptiveClusterEliminationConfiguration = (
        AdaptiveClusterEliminationConfiguration()
    )

    @classmethod
    def from_mapping(
        cls, value: dict[str, Any] | None,
    ) -> "ContainerEliminationConfiguration":
        raw = dict(value or {})
        enabled = _strict_bool(raw.get("enabled", False), "container_elimination.enabled")
        maximum_targets = _positive_int(
            raw.get("maximum_target_containers", 8),
            "container_elimination.maximum_target_containers",
        )
        maximum_candidates = _positive_int(
            raw.get("maximum_candidates", 1024),
            "container_elimination.maximum_candidates",
        )
        legacy = {
            "maximum_partial_repack_items", "destination_candidate_limit",
        } & raw.keys()
        if legacy:
            raise ValueError(
                "Legacy container-elimination setting(s) were replaced by "
                "adaptive_cluster_elimination: " + ", ".join(sorted(legacy))
            )
        fractions_raw = raw.get("phase_time_fractions", [0.35, 0.25, 0.40])
        if not isinstance(fractions_raw, list | tuple) or len(fractions_raw) != 3:
            raise ValueError(
                "container_search.consolidation.container_elimination."
                "phase_time_fractions must contain exactly three values"
            )
        fractions = tuple(
            _finite_float(value, "container_elimination.phase_time_fractions")
            for value in fractions_raw
        )
        if any(value <= 0 for value in fractions) or abs(sum(fractions) - 1.0) > 1e-9:
            raise ValueError(
                "container_search.consolidation.container_elimination."
                "phase_time_fractions must be positive and sum to 1"
            )
        adaptive = AdaptiveClusterEliminationConfiguration.from_mapping(
            raw.get("adaptive_cluster_elimination")
        )
        return cls(enabled, maximum_targets, maximum_candidates, fractions, adaptive)

    def metadata(self) -> dict[str, object]:
        return {
            "container_elimination_enabled": self.enabled,
            "container_elimination_maximum_target_containers": self.maximum_target_containers,
            "container_elimination_maximum_candidates": self.maximum_candidates,
            "container_elimination_phase_time_fractions": list(self.phase_time_fractions),
            **self.adaptive_cluster_elimination.metadata(),
        }


@dataclass(frozen=True)
class ConsolidationConfiguration:
    """Ngân sách thử đóng bớt container sau construction đầu tiên."""

    enabled: bool = False
    time_limit_seconds: float = 10.0
    max_candidates: int = 128
    item_order_variants: tuple[str, ...] = (
        "current", "decreasing_volume", "decreasing_weight", "support_difficulty",
    )
    container_elimination: ContainerEliminationConfiguration = (
        ContainerEliminationConfiguration()
    )

    @classmethod
    def from_mapping(cls, value: dict[str, Any] | None) -> "ConsolidationConfiguration":
        raw = dict(value or {})
        enabled = _strict_bool(raw.get("enabled", False), "consolidation.enabled")
        time_limit = _finite_float(
            raw.get("time_limit_seconds", 10.0), "consolidation.time_limit_seconds",
        )
        if time_limit <= 0:
            raise ValueError("container_search.consolidation.time_limit_seconds must be positive")
        max_candidates = _positive_int(
            raw.get("max_candidates", 128), "consolidation.max_candidates",
        )
        variants_raw = raw.get("item_order_variants", cls.item_order_variants)
        if not isinstance(variants_raw, list | tuple) or not variants_raw:
            raise ValueError(
                "container_search.consolidation.item_order_variants must be a non-empty list"
            )
        allowed = {"current", "decreasing_volume", "decreasing_weight", "support_difficulty"}
        variants = tuple(str(item) for item in variants_raw)
        unknown = sorted(set(variants) - allowed)
        if unknown:
            raise ValueError(
                "Unsupported container consolidation item order(s): " + ", ".join(unknown)
            )
        if len(set(variants)) != len(variants):
            raise ValueError("container_search.consolidation.item_order_variants contains duplicates")
        if "maximum_cardinality_reductions" in raw:
            raise ValueError(
                "container_search.consolidation.maximum_cardinality_reductions "
                "đã được thay thế; canonical incumbent improvement luôn xét tới "
                "capacity lower bound trong candidate/time budget."
            )
        elimination = ContainerEliminationConfiguration.from_mapping(
            raw.get("container_elimination")
        )
        return cls(enabled, time_limit, max_candidates, variants, elimination)

    def metadata(self) -> dict[str, object]:
        return {
            "container_consolidation_enabled": self.enabled,
            "container_consolidation_time_limit_seconds": self.time_limit_seconds,
            "container_consolidation_max_candidates": self.max_candidates,
            "container_consolidation_target_mode": "capacity_lower_bound",
            "container_consolidation_item_order_variants": list(self.item_order_variants),
            **self.container_elimination.metadata(),
        }


@dataclass(frozen=True)
class ContainerSearchConfiguration:
    """Cấu hình promotion an toàn của inventory-aware subset search."""

    enabled: bool
    limits: InventorySearchLimits
    exhaustive_max_containers: int = 10
    max_candidates_per_count: int = 32
    neighborhood_width: int = 8
    composition_beam_width: int = 64
    soft_volume_buffer_ratio: float = 0.10
    time_limit_seconds: float | None = None
    validation_reserve_seconds: float = 2.0
    construction_item_order_variants: tuple[str, ...] = (
        "current", "decreasing_weight", "support_difficulty",
    )
    consolidation: ConsolidationConfiguration = ConsolidationConfiguration()

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
        composition_beam_width = _positive_int(
            raw.get("composition_beam_width", 64),
            "composition_beam_width",
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
        validation_reserve = _non_negative_float(
            raw.get("validation_reserve_seconds", 2.0),
            "validation_reserve_seconds",
        )
        if time_limit is not None and validation_reserve >= time_limit:
            raise ValueError(
                "container_search.validation_reserve_seconds must be smaller "
                "than time_limit_seconds"
            )
        variants = _item_order_variants(
            raw.get(
                "construction_item_order_variants",
                cls.construction_item_order_variants,
            )
        )
        consolidation = ConsolidationConfiguration.from_mapping(raw.get("consolidation"))
        adaptive = consolidation.container_elimination.adaptive_cluster_elimination
        if (
            adaptive.enabled
            and adaptive.minimum_validation_reserve_seconds > validation_reserve
        ):
            raise ValueError(
                "adaptive_cluster_elimination.minimum_validation_reserve_seconds "
                "must not exceed container_search.validation_reserve_seconds"
            )
        if (
            time_limit is not None
            and consolidation.enabled
            and validation_reserve + consolidation.time_limit_seconds >= time_limit
        ):
            raise ValueError(
                "container_search requires time_limit_seconds greater than the "
                "sum of validation_reserve_seconds and consolidation.time_limit_seconds"
            )
        return cls(
            enabled=enabled,
            limits=InventorySearchLimits(initial, maximum, automatically_increase),
            exhaustive_max_containers=exhaustive,
            max_candidates_per_count=candidate_limit,
            neighborhood_width=neighborhood_width,
            composition_beam_width=composition_beam_width,
            soft_volume_buffer_ratio=soft_buffer,
            time_limit_seconds=time_limit,
            validation_reserve_seconds=validation_reserve,
            construction_item_order_variants=variants,
            consolidation=consolidation,
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
            "container_search_execution_mode": "bounded_search",
            "container_search_unlimited_time": self.time_limit_seconds is None,
            "container_search_validation_reserve_seconds": (
                self.validation_reserve_seconds
            ),
            "container_search_composition_beam_width": self.composition_beam_width,
            "container_search_construction_item_order_variants": list(
                self.construction_item_order_variants
            ),
            **self.consolidation.metadata(),
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


def _non_negative_float(value: object, name: str) -> float:
    parsed = _finite_float(value, name)
    if parsed < 0:
        raise ValueError(f"container_search.{name} must be non-negative")
    return parsed


def _item_order_variants(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple) or not value:
        raise ValueError(
            "container_search.construction_item_order_variants must be a non-empty list"
        )
    variants = tuple(str(item) for item in value)
    allowed = {"current", "decreasing_volume", "decreasing_weight", "support_difficulty"}
    unknown = sorted(set(variants) - allowed)
    if unknown:
        raise ValueError(
            "Unsupported inventory construction item order(s): " + ", ".join(unknown)
        )
    if len(set(variants)) != len(variants):
        raise ValueError(
            "container_search.construction_item_order_variants contains duplicates"
        )
    return variants


def _strict_bool(value: object, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"container_search.{name} must be true or false")
    return value
