"""Deterministic container-subset policies for constructive packing engines.

The legacy policy is intentionally preserved for Levels 1--7.  Level 8 uses
the adaptive policy: exact enumeration for small heterogeneous catalogs and a
bounded, diverse candidate portfolio for larger catalogs.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from itertools import combinations
from typing import Protocol

from ...schemas import Container, Item


class ContainerSubsetSelectionPolicy(Protocol):
    """Provide cardinality-ordered candidate container subsets."""

    def candidates(
        self, containers: list[Container], items: list[Item]
    ) -> Iterable[tuple[Container, ...]]: ...

    def metadata(self) -> dict[str, object]: ...


def _subset_sort_key(subset: tuple[Container, ...]) -> tuple[object, ...]:
    return (
        sum(value.cost for value in subset),
        sum(value.volume_m3 for value in subset),
        tuple(sorted(value.container_id for value in subset)),
    )


def _ordering_portfolio(containers: list[Container]) -> tuple[tuple[Container, ...], ...]:
    total_weight = max(sum(value.max_weight_kg for value in containers), 1.0)
    total_volume = max(sum(value.volume_m3 for value in containers), 1.0)
    orderings = (
        tuple(sorted(containers, key=lambda value: (value.cost, value.container_id))),
        tuple(sorted(containers, key=lambda value: (-value.max_weight_kg, value.cost, value.container_id))),
        tuple(sorted(containers, key=lambda value: (-value.volume_m3, value.cost, value.container_id))),
        tuple(sorted(
            containers,
            key=lambda value: (
                value.cost / max(value.max_weight_kg / total_weight, 1e-12),
                value.container_id,
            ),
        )),
        tuple(sorted(
            containers,
            key=lambda value: (
                value.cost / max(value.volume_m3 / total_volume, 1e-12),
                value.container_id,
            ),
        )),
        tuple(sorted(
            containers,
            key=lambda value: (
                -(
                    value.max_weight_kg / total_weight
                    + value.volume_m3 / total_volume
                ),
                value.cost,
                value.container_id,
            ),
        )),
    )
    unique: list[tuple[Container, ...]] = []
    seen: set[tuple[str, ...]] = set()
    for ordering in orderings:
        signature = tuple(value.container_id for value in ordering)
        if signature not in seen:
            seen.add(signature)
            unique.append(ordering)
    return tuple(unique)


@dataclass
class AdaptiveContainerSubsetSelectionPolicy:
    """Exact-small / bounded-large subset search in cardinality order.

    Aggregate payload and volume are safe necessary-condition filters.  The
    bounded branch deliberately keeps several cost/capacity orderings and
    their one-swap neighborhoods, rather than one arbitrary prefix.
    """

    exhaustive_max_containers: int = 8
    max_candidates_per_count: int = 32

    def __post_init__(self) -> None:
        if self.exhaustive_max_containers <= 0:
            raise ValueError("exhaustive_max_containers must be positive")
        if self.max_candidates_per_count <= 0:
            raise ValueError("max_candidates_per_count must be positive")
        self._mode = "not_run"
        self._generated = 0
        self._capacity_pruned = 0
        self._cardinalities = 0
        self._payload_lower_bound = 0
        self._volume_lower_bound = 0

    def candidates(
        self, containers: list[Container], items: list[Item]
    ) -> tuple[tuple[Container, ...], ...]:
        total_weight = sum(value.weight_kg for value in items)
        total_volume = sum(value.volume_m3 for value in items)
        exact = len(containers) <= self.exhaustive_max_containers
        self._mode = "exhaustive_small_catalog" if exact else "bounded_diverse_large_catalog"
        self._generated = 0
        self._capacity_pruned = 0
        self._cardinalities = 0
        self._payload_lower_bound = _capacity_lower_bound(
            total_weight,
            sorted(
                (value.max_weight_kg for value in containers), reverse=True
            ),
        )
        self._volume_lower_bound = _capacity_lower_bound(
            total_volume,
            sorted((value.volume_m3 for value in containers), reverse=True),
        )
        selected: list[tuple[Container, ...]] = []
        orderings = _ordering_portfolio(containers)

        for count in range(1, len(containers) + 1):
            self._cardinalities += 1
            if exact:
                candidates = list(combinations(containers, count))
            else:
                by_signature: dict[tuple[str, ...], tuple[Container, ...]] = {}
                for ordering in orderings:
                    base = tuple(ordering[:count])
                    signature = tuple(sorted(value.container_id for value in base))
                    by_signature[signature] = base
                    base_ids = {value.container_id for value in base}
                    outside = [value for value in ordering if value.container_id not in base_ids]
                    for removed in base:
                        for added in outside:
                            neighbor = tuple(
                                added if value.container_id == removed.container_id else value
                                for value in base
                            )
                            neighbor_signature = tuple(sorted(value.container_id for value in neighbor))
                            by_signature[neighbor_signature] = neighbor
                candidates = list(by_signature.values())

            feasible: list[tuple[Container, ...]] = []
            for subset in candidates:
                if sum(value.max_weight_kg for value in subset) + 1e-9 < total_weight:
                    self._capacity_pruned += 1
                    continue
                if sum(value.volume_m3 for value in subset) + 1e-12 < total_volume:
                    self._capacity_pruned += 1
                    continue
                feasible.append(tuple(sorted(subset, key=lambda value: value.container_id)))
            feasible.sort(key=_subset_sort_key)
            if not exact:
                feasible = feasible[: self.max_candidates_per_count]
            selected.extend(feasible)

        self._generated = len(selected)
        return tuple(selected)

    def metadata(self) -> dict[str, object]:
        return {
            "container_subset_policy": "adaptive_exact_small_bounded_diverse_large_v1",
            "container_subset_search_mode": self._mode,
            "container_subset_exhaustive_max_containers": self.exhaustive_max_containers,
            "container_subset_max_candidates_per_count": self.max_candidates_per_count,
            "container_subset_candidates_generated": self._generated,
            "container_subset_capacity_pruned": self._capacity_pruned,
            "container_subset_cardinalities_considered": self._cardinalities,
            "container_subset_payload_lower_bound": self._payload_lower_bound,
            "container_subset_volume_lower_bound": self._volume_lower_bound,
            "container_subset_aggregate_lower_bound": max(
                self._payload_lower_bound, self._volume_lower_bound
            ),
        }


def _capacity_lower_bound(required: float, capacities: list[float]) -> int:
    if required <= 0:
        return 0
    accumulated = 0.0
    for count, capacity in enumerate(capacities, start=1):
        accumulated += capacity
        if accumulated + 1e-12 >= required:
            return count
    return len(capacities) + 1
