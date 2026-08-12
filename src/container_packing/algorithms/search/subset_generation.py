"""Lazy, cardinality-first container-subset generation có giới hạn."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from itertools import combinations
from math import ceil, comb
from time import perf_counter

from ..orientation import OrientationProvider, fixed_orientation_provider
from ...schemas import Container, Item
from .inventory import (
    ContainerTypeComposition,
    InventorySearchLimits,
    NormalizedContainerInventory,
    normalize_container_inventory,
)
from .precheck import container_volume_m3, estimate_container_lower_bound


def midpoint_cardinality_ladder(minimum: int, maximum: int) -> tuple[int, ...]:
    """Ladder tăng nhanh tới cap để lấy incumbent trước khi tối ưu ngược."""

    if minimum <= 0 or maximum <= 0 or minimum > maximum:
        raise ValueError("cardinality ladder requires 0 < minimum <= maximum")
    values = [minimum]
    current = minimum
    while current < maximum:
        current = max(current + 1, ceil((current + maximum) / 2))
        values.append(current)
    return tuple(values)


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
    composition_beam_width: int = 64
    soft_volume_buffer_ratio: float = 0.10
    deadline_monotonic: float | None = None
    monotonic_clock: Callable[[], float] = perf_counter
    candidate_mode: str = "portfolio"
    cardinalities_override: tuple[int, ...] | None = None

    def __post_init__(self) -> None:
        if self.exhaustive_max_containers <= 0:
            raise ValueError("exhaustive_max_containers must be positive")
        if self.max_candidates_per_count <= 0:
            raise ValueError("max_candidates_per_count must be positive")
        if self.neighborhood_width <= 0:
            raise ValueError("neighborhood_width must be positive")
        if self.composition_beam_width <= 0:
            raise ValueError("composition_beam_width must be positive")
        if not 0 <= self.soft_volume_buffer_ratio <= 1:
            raise ValueError("soft_volume_buffer_ratio must be in [0, 1]")
        if self.candidate_mode not in {"portfolio", "incumbent_acquisition"}:
            raise ValueError(
                "candidate_mode must be portfolio or incumbent_acquisition"
            )
        if self.cardinalities_override is not None:
            if (
                not self.cardinalities_override
                or any(value <= 0 for value in self.cardinalities_override)
                or tuple(sorted(set(self.cardinalities_override)))
                != self.cardinalities_override
            ):
                raise ValueError(
                    "cardinalities_override must be positive, unique and increasing"
                )
        self._mode = "not_run"
        self._generated = 0
        self._capacity_pruned = 0
        self._compatibility_pruned = 0
        self._deadline_reached = False
        self._duplicate_physical_subsets_avoided = 0
        self._compositions_generated = 0
        self._compositions_by_cardinality: dict[int, int] = {}
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
        requested_cardinalities = (
            self.limits.cardinalities
            if self.cardinalities_override is None
            else self.cardinalities_override
        )
        cardinalities = tuple(
            value for value in requested_cardinalities
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
        self._duplicate_physical_subsets_avoided = 0
        self._compositions_generated = 0
        self._compositions_by_cardinality = {}
        for count in cardinalities:
            if self._expired():
                return
            raw = self._raw_candidates(inventory, count, items)
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
            self._compositions_by_cardinality[count] = len(ranked)
            ranked.sort(key=lambda value: value[0])
            if (
                self.candidate_mode == "incumbent_acquisition"
                and inventory.physical_container_count > self.exhaustive_max_containers
            ):
                capacity_anchor = min(
                    ranked,
                    key=lambda value: self._acquisition_capacity_rank(
                        value[1], items,
                    ),
                    default=None,
                )
                cost_candidate = None if not ranked else ranked[0]
                selected_ranked = []
                signatures: set[tuple[str, ...]] = set()
                for value in (capacity_anchor, cost_candidate):
                    if value is None:
                        continue
                    signature = tuple(
                        item.container_id for item in value[1]
                    )
                    if signature in signatures:
                        continue
                    signatures.add(signature)
                    selected_ranked.append(value)
                    if len(selected_ranked) >= self.max_candidates_per_count:
                        break
                ordered = selected_ranked
                for _, subset in ordered:
                    if self._expired():
                        return
                    self._generated += 1
                    yield subset
                continue
            limit = (
                len(ranked)
                if inventory.physical_container_count <= self.exhaustive_max_containers
                else self.max_candidates_per_count
            )
            selected_ranked = ranked[:limit]
            if inventory.physical_container_count > self.exhaustive_max_containers:
                # Giữ các composition thuần loại làm anchor capacity. Nếu chỉ
                # lấy top-cost, các type lớn/đắt nhưng cần thiết cho geometry
                # có thể bị loại trước khi constructive solver được thử.
                type_by_id = inventory.type_id_by_container_id
                homogeneous = [
                    value for value in ranked
                    if len({type_by_id[item.container_id] for item in value[1]}) == 1
                ]
                merged = {
                    tuple(item.container_id for item in subset): (score, subset)
                    for score, subset in (*homogeneous, *selected_ranked)
                }
                selected_ranked = sorted(merged.values(), key=lambda value: value[0])
                if len(selected_ranked) > limit:
                    mandatory = {
                        tuple(item.container_id for item in subset)
                        for _, subset in homogeneous
                    }
                    keep = [
                        value for value in selected_ranked
                        if tuple(item.container_id for item in value[1]) in mandatory
                    ]
                    keep_signatures = {
                        tuple(item.container_id for item in value[1]) for value in keep
                    }
                    keep.extend(
                        value for value in selected_ranked
                        if tuple(item.container_id for item in value[1]) not in keep_signatures
                    )
                    selected_ranked = sorted(keep[:limit], key=lambda value: value[0])
            # Chỉ materialize một cardinality tại một thời điểm. Caller có thể
            # dừng iterator mà không phải dựng lịch cho các cardinality sau.
            ordered = selected_ranked
            if inventory.physical_container_count > self.exhaustive_max_containers:
                type_by_id = inventory.type_id_by_container_id
                homogeneous = [
                    value for value in selected_ranked
                    if len({type_by_id[item.container_id] for item in value[1]}) == 1
                ]
                anchor = None if not homogeneous else max(
                    homogeneous,
                    key=lambda value: (
                        sum(container_volume_m3(item) for item in value[1]),
                        sum(item.max_weight_kg for item in value[1]),
                        -sum(item.cost for item in value[1]),
                    ),
                )
                if anchor is not None:
                    ordered = [anchor] + [
                        value for value in selected_ranked if value != anchor
                    ]
            for _, subset in ordered:
                if self._expired():
                    return
                self._generated += 1
                yield subset

    def _raw_candidates(
        self, inventory: NormalizedContainerInventory, count: int,
        items: list[Item],
    ) -> Iterable[tuple[Container, ...]]:
        values = list(inventory.available_containers)
        if len(values) <= self.exhaustive_max_containers:
            return combinations(values, count)

        compositions = self._composition_candidates(inventory, count, items)
        self._compositions_generated += len(compositions)
        materialized: list[tuple[Container, ...]] = []
        for composition in compositions:
            multiplicity = 1
            groups = inventory.groups_by_type_id
            for type_id, quantity in composition.quantities:
                multiplicity *= comb(groups[type_id].quantity, quantity)
            self._duplicate_physical_subsets_avoided += max(0, multiplicity - 1)
            materialized.append(inventory.materialize(composition))
        return tuple(materialized)

    def _composition_candidates(
        self,
        inventory: NormalizedContainerInventory,
        count: int,
        items: list[Item],
    ) -> tuple[ContainerTypeComposition, ...]:
        """Sinh portfolio composition bounded, không duyệt tổ hợp physical ID."""
        groups = inventory.groups
        if count == 1:
            return tuple(
                ContainerTypeComposition.from_counts({group.type_id: 1})
                for group in groups
            )

        required_volume = sum(value.volume_m3 for value in items)
        required_payload = sum(value.weight_kg for value in items)
        candidates: dict[
            tuple[tuple[str, int], ...], ContainerTypeComposition
        ] = {}

        # Seed cực trị bảo toàn đa dạng cost/capacity trước khi beam ranking.
        for ordering in self._group_orderings(groups):
            remaining = count
            counts: dict[str, int] = {}
            for group in ordering:
                take = min(group.quantity, remaining)
                if take:
                    counts[group.type_id] = take
                    remaining -= take
                if remaining == 0:
                    composition = ContainerTypeComposition.from_counts(counts)
                    candidates[composition.signature] = composition
                    break

        states: dict[tuple[int, ...], tuple[int, ...]] = {
            tuple(0 for _ in groups): tuple(0 for _ in groups)
        }
        beam_width = max(
            self.composition_beam_width,
            self.max_candidates_per_count * 2,
        )
        for _ in range(count):
            if self._expired():
                break
            expanded: dict[tuple[int, ...], tuple[int, ...]] = {}
            for state in states.values():
                for index, group in enumerate(groups):
                    if state[index] >= group.quantity:
                        continue
                    candidate = list(state)
                    candidate[index] += 1
                    signature = tuple(candidate)
                    expanded.setdefault(signature, signature)
            ranked = sorted(
                expanded.values(),
                key=lambda state: self._partial_composition_score(
                    state, groups, required_volume, required_payload,
                ),
            )
            states = {state: state for state in ranked[:beam_width]}

        for state in states.values():
            if sum(state) != count:
                continue
            composition = ContainerTypeComposition.from_counts({
                group.type_id: quantity
                for group, quantity in zip(groups, state)
            })
            candidates[composition.signature] = composition

        # Một-unit transfer quanh seed/beam giúp tránh một portfolio quá thuần loại.
        bases = list(candidates.values())
        group_by_id = inventory.groups_by_type_id
        for base in bases[: self.neighborhood_width]:
            counts = dict(base.quantities)
            for source_id, source_quantity in base.quantities:
                for target in groups:
                    if target.type_id == source_id:
                        continue
                    if counts.get(target.type_id, 0) >= target.quantity:
                        continue
                    neighbor = dict(counts)
                    neighbor[source_id] = source_quantity - 1
                    if neighbor[source_id] == 0:
                        del neighbor[source_id]
                    neighbor[target.type_id] = neighbor.get(target.type_id, 0) + 1
                    composition = ContainerTypeComposition.from_counts(neighbor)
                    if all(
                        quantity <= group_by_id[type_id].quantity
                        for type_id, quantity in composition.quantities
                    ):
                        candidates.setdefault(composition.signature, composition)
        return tuple(sorted(candidates.values(), key=lambda value: value.signature))

    @staticmethod
    def _group_orderings(groups) -> tuple[tuple[object, ...], ...]:
        values = tuple(groups)
        orderings = (
            tuple(sorted(values, key=lambda value: (
                value.representative.cost, value.type_id,
            ))),
            tuple(sorted(values, key=lambda value: (
                -container_volume_m3(value.representative),
                value.representative.cost, value.type_id,
            ))),
            tuple(sorted(values, key=lambda value: (
                -value.representative.max_weight_kg,
                value.representative.cost, value.type_id,
            ))),
            tuple(sorted(values, key=lambda value: (
                value.representative.cost
                / max(container_volume_m3(value.representative), 1e-12),
                value.type_id,
            ))),
        )
        unique: dict[tuple[str, ...], tuple[object, ...]] = {}
        for ordering in orderings:
            unique.setdefault(tuple(value.type_id for value in ordering), ordering)
        return tuple(unique.values())

    @staticmethod
    def _partial_composition_score(
        state, groups, required_volume: float, required_payload: float,
    ) -> tuple[object, ...]:
        volume = sum(
            quantity * container_volume_m3(group.representative)
            for group, quantity in zip(groups, state)
        )
        payload = sum(
            quantity * group.representative.max_weight_kg
            for group, quantity in zip(groups, state)
        )
        cost = sum(
            quantity * group.representative.cost
            for group, quantity in zip(groups, state)
        )
        volume_deficit = max(0.0, required_volume - volume) / max(required_volume, 1e-12)
        payload_deficit = max(0.0, required_payload - payload) / max(required_payload, 1e-12)
        return (
            volume_deficit + payload_deficit,
            max(volume_deficit, payload_deficit),
            cost,
            abs(volume - required_volume),
            abs(payload - required_payload),
            tuple(state),
        )

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

    @staticmethod
    def _acquisition_capacity_rank(
        subset: tuple[Container, ...], items: list[Item],
    ) -> tuple[object, ...]:
        required_volume = sum(value.volume_m3 for value in items)
        required_payload = sum(value.weight_kg for value in items)
        total_volume = sum(container_volume_m3(value) for value in subset)
        total_payload = sum(value.max_weight_kg for value in subset)
        volume_ratio = total_volume / max(required_volume, 1e-12)
        payload_ratio = total_payload / max(required_payload, 1e-12)
        return (
            -min(volume_ratio, payload_ratio),
            -max(container_volume_m3(value) for value in subset),
            -max(value.max_weight_kg for value in subset),
            -total_volume,
            -total_payload,
            sum(value.cost for value in subset),
            tuple(value.container_id for value in subset),
        )

    def _expired(self) -> bool:
        if self.deadline_monotonic is None:
            return False
        if self.monotonic_clock() < self.deadline_monotonic:
            return False
        self._deadline_reached = True
        return True

    def metadata(self) -> dict[str, object]:
        inventory = self._inventory
        lower_bound = self._lower_bound
        return {
            "container_subset_policy": "lazy_ranked_inventory_aware_v1",
            "container_subset_search_mode": self._mode,
            "container_subset_scheduling": (
                "capacity_rich_then_cost_acquisition"
                if self.candidate_mode == "incumbent_acquisition"
                else "capacity_anchor_each_cardinality_then_cost_portfolio"
                if self._mode == "bounded_lazy_large_inventory"
                else "strict_cardinality_order"
            ),
            "container_subset_candidate_mode": self.candidate_mode,
            "container_subset_candidates_generated": self._generated,
            "container_subset_capacity_pruned": self._capacity_pruned,
            "container_subset_compatibility_pruned": self._compatibility_pruned,
            "container_subset_deadline_reached": self._deadline_reached,
            "container_type_compositions_generated": self._compositions_generated,
            "container_type_compositions_by_cardinality": dict(
                self._compositions_by_cardinality
            ),
            "duplicate_physical_subsets_avoided": (
                self._duplicate_physical_subsets_avoided
            ),
            "container_composition_beam_width": self.composition_beam_width,
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
