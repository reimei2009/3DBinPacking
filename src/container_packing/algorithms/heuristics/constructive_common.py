"""Shared non-geometric utilities for deterministic constructive heuristics."""

from __future__ import annotations

from itertools import combinations
from typing import Iterable

from ...schemas import Container, Item


def item_sort_key(item: Item) -> tuple[float, float, float, str]:
    volume = item.length_mm * item.width_mm * item.height_mm
    return (-volume, -max(item.length_mm, item.width_mm, item.height_mm), -item.weight_kg, item.item_id)


def container_orders(containers: tuple[Container, ...]) -> list[tuple[Container, ...]]:
    candidates = [
        tuple(sorted(containers, key=lambda value: (value.cost, value.volume_m3, value.container_id))),
        tuple(sorted(containers, key=lambda value: (value.volume_m3, value.cost, value.container_id))),
        tuple(sorted(containers, key=lambda value: (-value.volume_m3, value.cost, value.container_id))),
        tuple(sorted(containers, key=lambda value: (-value.max_weight_kg, -value.volume_m3, value.container_id))),
    ]
    unique: list[tuple[Container, ...]] = []
    seen: set[tuple[str, ...]] = set()
    for candidate in candidates:
        signature = tuple(value.container_id for value in candidate)
        if signature not in seen:
            seen.add(signature)
            unique.append(candidate)
    return unique


def candidate_subsets(containers: list[Container], limit: int) -> Iterable[tuple[Container, ...]]:
    if len(containers) <= limit:
        for count in range(1, len(containers) + 1):
            values = list(combinations(containers, count))
            values.sort(key=lambda subset: (
                sum(value.cost for value in subset),
                sum(value.volume_m3 for value in subset),
                tuple(value.container_id for value in subset),
            ))
            yield from values
        return
    orderings = [
        sorted(containers, key=lambda value: (value.cost, value.volume_m3, value.container_id)),
        sorted(containers, key=lambda value: (value.volume_m3, value.cost, value.container_id)),
        sorted(containers, key=lambda value: (-value.volume_m3, value.cost, value.container_id)),
        sorted(containers, key=lambda value: (-value.max_weight_kg, value.cost, value.container_id)),
    ]
    seen: set[tuple[str, ...]] = set()
    for count in range(1, len(containers) + 1):
        candidates: list[tuple[Container, ...]] = []
        for ordering in orderings:
            subset = tuple(ordering[:count])
            signature = tuple(sorted(value.container_id for value in subset))
            if signature not in seen:
                seen.add(signature)
                candidates.append(subset)
        candidates.sort(key=lambda subset: (
            sum(value.cost for value in subset), tuple(value.container_id for value in subset)
        ))
        yield from candidates
