"""Shared destroy-and-repair neighborhoods for Extreme-Point searches."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...schemas import Container, Item, Placement
from ...metrics import packing_tiebreak_metrics
from .extreme_point_core import (
    SearchStats,
    candidate_subsets,
    container_orders,
    pack_order_first_fit,
)


@dataclass
class RepackingStats:
    repacking_attempts: int = 0


def solution_score(placements: list[Placement], containers: list[Container]) -> tuple[float, ...]:
    """Lexicographic count, cost, occupied bounding volume, coordinate score."""
    used_ids = {value.container_id for value in placements}
    costs = {value.container_id: value.cost for value in containers}
    bounding_volume, coordinate_score = packing_tiebreak_metrics(placements)
    return float(len(used_ids)), float(sum(costs[value] for value in used_ids)), bounding_volume, coordinate_score


def generate_neighbor_orders(
    current_order: list[Item], placements: list[Placement], max_neighbors: int,
) -> list[tuple[str, list[Item]]]:
    """Generate deterministic relocate, swap, and reinsert neighborhoods."""
    if max_neighbors <= 0:
        return []
    item_map = {value.item_id: value for value in current_order}
    base_ids = [value.item_id for value in current_order]
    candidates: list[tuple[str, list[Item]]] = []
    seen = {tuple(base_ids)}

    def add(label: str, identifiers: list[str]) -> None:
        signature = tuple(identifiers)
        if len(candidates) >= max_neighbors or signature in seen:
            return
        seen.add(signature)
        candidates.append((label, [item_map[value] for value in identifiers]))

    groups: dict[str, list[str]] = {}
    for placement in placements:
        groups.setdefault(placement.container_id, []).append(placement.item_id)
    for container_id, identifiers in sorted(groups.items(), key=lambda value: (len(value[1]), value[0])):
        moved = set(identifiers)
        add(f"relocate_from_{container_id}", [value for value in base_ids if value not in moved] + identifiers)

    for index in range(len(base_ids) - 1):
        values = list(base_ids)
        values[index], values[index + 1] = values[index + 1], values[index]
        add("swap_adjacent", values)

    for index in range(len(base_ids)):
        value = base_ids[index]
        remaining = base_ids[:index] + base_ids[index + 1:]
        add("reinsert_front", [value, *remaining])
        add("reinsert_back", [*remaining, value])
    return candidates


def subset_pool(
    containers: list[Container], placements: list[Placement], items: list[Item],
    enumeration_limit: int, candidate_limit: int, tolerance: float, *, allow_worse: bool = False,
) -> list[tuple[Container, ...]]:
    """Return capacity-feasible subsets, optionally including worse incumbents."""
    used_ids = {value.container_id for value in placements}
    current_count = len(used_ids)
    current_cost = sum(value.cost for value in containers if value.container_id in used_ids)
    total_weight = sum(value.weight_kg for value in items)
    total_volume = sum(value.volume_m3 for value in items)
    values: list[tuple[Container, ...]] = []
    for subset in candidate_subsets(containers, enumeration_limit):
        subset_cost = sum(value.cost for value in subset)
        if not allow_worse and (
            len(subset) > current_count or (len(subset) == current_count and subset_cost > current_cost)
        ):
            continue
        if sum(value.max_weight_kg for value in subset) + tolerance < total_weight:
            continue
        if sum(value.volume_m3 for value in subset) + tolerance < total_volume:
            continue
        values.append(subset)
    values.sort(key=lambda subset: (
        len(subset), sum(value.cost for value in subset),
        sum(value.volume_m3 for value in subset), tuple(value.container_id for value in subset),
    ))
    current_subset = tuple(value for value in containers if value.container_id in used_ids)
    selected = values[:candidate_limit]
    if current_subset and not any({value.container_id for value in subset} == used_ids for subset in selected):
        selected.append(current_subset)
    return selected


def repack_neighbor(
    item_order: list[Item], containers: list[Container], current: list[Placement],
    settings: dict[str, Any], stats: RepackingStats,
) -> list[Placement] | None:
    """Rebuild an item permutation with Extreme Points on candidate subsets."""
    tolerance = float(settings.get("coordinate_tolerance_mm", 1e-6))
    subsets = subset_pool(
        containers, current, item_order,
        int(settings.get("subset_enumeration_limit", 12)),
        int(settings.get("subset_candidate_limit", 48)), tolerance,
        allow_worse=bool(settings.get("allow_worse_subsets", False)),
    )
    for subset in subsets:
        for order in container_orders(subset):
            stats.repacking_attempts += 1
            candidate = pack_order_first_fit(item_order, order, tolerance, SearchStats())
            if candidate is not None:
                return candidate
    return None
