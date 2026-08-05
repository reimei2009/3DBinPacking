"""Lazy, cardinality-first container-subset generation có giới hạn."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from itertools import combinations
from time import perf_counter

from ..orientation import OrientationProvider, fixed_orientation_provider
from ...schemas import Container, Item
from .inventory import (
    InventorySearchLimits,
    NormalizedContainerInventory,
    normalize_container_inventory,
)
from .precheck import container_volume_m3, estimate_container_lower_bound


@dataclass
class LazyRankedContainerSubsetPolicy:
    """Sinh subset theo cardinality mà không tạo toàn bộ power set.

    Small inventory được exact theo từng cardinality. Large inventory dùng
    representative type cho singleton và một portfolio prefix/one-swap có
    giới hạn cho cardinality lớn hơn.
    """

    limits: InventorySearchLimits
    orientation_provider: OrientationProvider | None = None
    exhaustive_max_containers: int = 10
    max_candidates_per_count: int = 32
    neighborhood_width: int = 8
    soft_volume_buffer_ratio: float = 0.10
    deadline_monotonic: float | None = None

    def __post_init__(self) -> None:
        if self.exhaustive_max_containers <= 0:
            raise ValueError("exhaustive_max_containers must be positive")
        if self.max_candidates_per_count <= 0:
            raise ValueError("max_candidates_per_count must be positive")
        if self.neighborhood_width <= 0:
            raise ValueError("neighborhood_width must be positive")
        if not 0 <= self.soft_volume_buffer_ratio <= 1:
            raise ValueError("soft_volume_buffer_ratio must be in [0, 1]")
        self._mode = "not_run"
        self._generated = 0
        self._capacity_pruned = 0
        self._compatibility_pruned = 0
        self._deadline_reached = False
        self._inventory: NormalizedContainerInventory | None = None
        self._lower_bound = None
        self._cardinalities_considered: tuple[int, ...] = ()

    def candidates(
        self, containers: list[Container], items: list[Item],
    ) -> Iterable[tuple[Container, ...]]:
        return self.iter_candidates(containers, items)

    def iter_candidates(
        self, containers: list[Container], items: list[Item],
    ) -> Iterator[tuple[Container, ...]]:
        self._inventory = normalize_container_inventory(containers)
        inventory = self._inventory
        provider = self.orientation_provider or fixed_orientation_provider()
        lower_bound = estimate_container_lower_bound(items, inventory)
        self._lower_bound = lower_bound
        minimum = max(
            self.limits.initial_used_container_count,
            lower_bound.aggregate_lower_bound,
        )
        cardinalities = tuple(
            value for value in self.limits.cardinalities
            if minimum <= value <= inventory.physical_container_count
        )
        self._cardinalities_considered = cardinalities
        self._mode = (
            "exhaustive_by_cardinality"
            if inventory.physical_container_count <= self.exhaustive_max_containers
            else "bounded_lazy_large_inventory"
        )
        self._generated = 0
        self._capacity_pruned = 0
        self._compatibility_pruned = 0
        self._deadline_reached = False

        for count in cardinalities:
            if self._expired():
                return
            raw = self._raw_candidates(inventory, count)
            ranked: list[tuple[tuple[object, ...], tuple[Container, ...]]] = []
            seen: set[tuple[str, ...]] = set()
            for subset in raw:
                if self._expired():
                    return
                canonical = tuple(sorted(subset, key=lambda value: value.container_id))
                signature = tuple(value.container_id for value in canonical)
                if signature in seen:
                    continue
                seen.add(signature)
                if not self._aggregate_capacity_allows(canonical, items):
                    self._capacity_pruned += 1
                    continue
                if not self._individual_compatibility_allows(
                    canonical, items, provider,
                ):
                    self._compatibility_pruned += 1
                    continue
                ranked.append((self._score(canonical, items), canonical))
            ranked.sort(key=lambda value: value[0])
            limit = (
                len(ranked)
                if inventory.physical_container_count <= self.exhaustive_max_containers
                else self.max_candidates_per_count
            )
            for _, subset in ranked[:limit]:
                self._generated += 1
                yield subset

    def _raw_candidates(
        self, inventory: NormalizedContainerInventory, count: int,
    ) -> Iterable[tuple[Container, ...]]:
        values = list(inventory.available_containers)
        if len(values) <= self.exhaustive_max_containers:
            return combinations(values, count)
        if count == 1:
            return tuple((group.representative,) for group in inventory.groups)

        orderings = self._orderings(values)
        candidates: dict[tuple[str, ...], tuple[Container, ...]] = {}
        for ordering in orderings:
            base = tuple(ordering[:count])
            candidates[tuple(sorted(value.container_id for value in base))] = base
            outside = ordering[count:count + self.neighborhood_width]
            for removed in base[-self.neighborhood_width:]:
                for added in outside:
                    neighbor = tuple(
                        added if value.container_id == removed.container_id else value
                        for value in base
                    )
                    candidates[
                        tuple(sorted(value.container_id for value in neighbor))
                    ] = neighbor
        return tuple(candidates.values())

    @staticmethod
    def _orderings(containers: list[Container]) -> tuple[tuple[Container, ...], ...]:
        candidates = (
            tuple(sorted(containers, key=lambda value: (value.cost, value.container_id))),
            tuple(sorted(containers, key=lambda value: (
                -container_volume_m3(value), value.cost, value.container_id,
            ))),
            tuple(sorted(containers, key=lambda value: (
                -value.max_weight_kg, value.cost, value.container_id,
            ))),
            tuple(sorted(containers, key=lambda value: (
                value.cost / max(container_volume_m3(value), 1e-12), value.container_id,
            ))),
        )
        unique: dict[tuple[str, ...], tuple[Container, ...]] = {}
        for value in candidates:
            unique.setdefault(tuple(item.container_id for item in value), value)
        return tuple(unique.values())

    @staticmethod
    def _aggregate_capacity_allows(
        subset: tuple[Container, ...], items: list[Item],
    ) -> bool:
        return (
            sum(container_volume_m3(value) for value in subset) + 1e-12
            >= sum(value.volume_m3 for value in items)
            and sum(value.max_weight_kg for value in subset) + 1e-9
            >= sum(value.weight_kg for value in items)
        )

    @staticmethod
    def _individual_compatibility_allows(
        subset: tuple[Container, ...], items: list[Item], provider: OrientationProvider,
    ) -> bool:
        return all(any(
            item.weight_kg <= container.max_weight_kg
            and any(
                dimensions.length_mm <= container.length_mm
                and dimensions.width_mm <= container.width_mm
                and dimensions.height_mm <= container.height_mm
                for dimensions in provider.candidates(item)
            )
            for container in subset
        ) for item in items)

    def _score(
        self, subset: tuple[Container, ...], items: list[Item],
    ) -> tuple[object, ...]:
        item_volume = sum(value.volume_m3 for value in items)
        subset_volume = sum(container_volume_m3(value) for value in subset)
        slack_ratio = max(0.0, subset_volume - item_volume) / max(subset_volume, 1e-12)
        soft_tightness_penalty = max(
            0.0, self.soft_volume_buffer_ratio - slack_ratio
        )
        return (
            sum(value.cost for value in subset),
            soft_tightness_penalty,
            subset_volume - item_volume,
            sum(value.max_weight_kg for value in subset)
            - sum(value.weight_kg for value in items),
            tuple(value.container_id for value in subset),
        )

    def _expired(self) -> bool:
        if self.deadline_monotonic is None:
            return False
        if perf_counter() < self.deadline_monotonic:
            return False
        self._deadline_reached = True
        return True

    def metadata(self) -> dict[str, object]:
        inventory = self._inventory
        lower_bound = self._lower_bound
        return {
            "container_subset_policy": "lazy_ranked_inventory_aware_v1",
            "container_subset_search_mode": self._mode,
            "container_subset_candidates_generated": self._generated,
            "container_subset_capacity_pruned": self._capacity_pruned,
            "container_subset_compatibility_pruned": self._compatibility_pruned,
            "container_subset_deadline_reached": self._deadline_reached,
            "container_subset_soft_volume_buffer_ratio": self.soft_volume_buffer_ratio,
            "container_subset_exhaustive_max_containers": self.exhaustive_max_containers,
            "container_subset_max_candidates_per_count": self.max_candidates_per_count,
            "container_subset_cardinalities_considered": list(
                self._cardinalities_considered
            ),
            "container_subset_payload_lower_bound": (
                0 if lower_bound is None else lower_bound.payload_lower_bound
            ),
            "container_subset_volume_lower_bound": (
                0 if lower_bound is None else lower_bound.volume_lower_bound
            ),
            "container_subset_aggregate_lower_bound": (
                0 if lower_bound is None else lower_bound.aggregate_lower_bound
            ),
            "inventory_physical_container_count": (
                0 if inventory is None else inventory.physical_container_count
            ),
            "inventory_equivalent_type_count": (
                0 if inventory is None else inventory.equivalent_type_count
            ),
            "initial_used_container_count": self.limits.initial_used_container_count,
            "max_used_container_count": self.limits.max_used_container_count,
            "automatically_increase_container_count": (
                self.limits.automatically_increase_container_count
            ),
        }
