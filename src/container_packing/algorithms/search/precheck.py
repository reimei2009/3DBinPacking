"""Hard precheck và lower bound an toàn cho inventory hữu hạn."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from math import isfinite

from ..orientation import OrientationProvider, fixed_orientation_provider
from ...schemas import Container, Item
from .inventory import NormalizedContainerInventory


def container_volume_m3(container: Container) -> float:
    """Tính volume từ canonical dimensions, không tin field derived bị cũ."""
    return (
        container.length_mm * container.width_mm * container.height_mm
        / 1_000_000_000.0
    )


@dataclass(frozen=True)
class HardPrecheckIssue:
    code: str
    message: str
    item_ids: tuple[str, ...] = ()
    container_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class HardPrecheckResult:
    valid: bool
    issues: tuple[HardPrecheckIssue, ...]
    compatible_container_ids_by_item: dict[str, tuple[str, ...]]
    total_item_volume_m3: float
    total_item_weight_kg: float
    total_inventory_volume_m3: float
    total_inventory_payload_kg: float


@dataclass(frozen=True)
class LowerBoundEstimate:
    volume_lower_bound: int
    payload_lower_bound: int
    aggregate_lower_bound: int
    inventory_physical_count: int
    attainable_by_aggregate_capacity: bool

    def metadata(self) -> dict[str, int | bool]:
        return {
            "volume_container_count_lower_bound": self.volume_lower_bound,
            "payload_container_count_lower_bound": self.payload_lower_bound,
            "container_count_lower_bound": self.aggregate_lower_bound,
            "lower_bound_inventory_physical_count": self.inventory_physical_count,
            "lower_bound_aggregate_capacity_attainable": (
                self.attainable_by_aggregate_capacity
            ),
        }


def _dimensions_fit(item: Item, container: Container, provider: OrientationProvider) -> bool:
    return any(
        value.length_mm <= container.length_mm
        and value.width_mm <= container.width_mm
        and value.height_mm <= container.height_mm
        for value in provider.candidates(item)
    )


def run_hard_precheck(
    items: list[Item],
    inventory: NormalizedContainerInventory,
    *,
    orientation_provider: OrientationProvider | None = None,
) -> HardPrecheckResult:
    """Chỉ kết luận các bất khả thi có chứng cứ chắc chắn từ input/capacity."""
    provider = orientation_provider or fixed_orientation_provider()
    issues: list[HardPrecheckIssue] = []
    item_ids = [value.item_id for value in items]
    duplicates = sorted(
        value for value, count in Counter(item_ids).items() if count > 1
    )
    if duplicates:
        issues.append(HardPrecheckIssue(
            "DUPLICATE_ITEM_ID",
            "Duplicate item IDs: " + ", ".join(duplicates),
            tuple(duplicates),
        ))

    compatible: dict[str, tuple[str, ...]] = {}
    for item in items:
        numeric = (
            item.length_mm, item.width_mm, item.height_mm, item.weight_kg,
        )
        if not all(isfinite(float(value)) for value in numeric):
            issues.append(HardPrecheckIssue(
                "INVALID_ITEM_VALUE", f"Item {item.item_id} contains NaN or infinity",
                (item.item_id,),
            ))
            compatible[item.item_id] = ()
            continue
        if min(item.length_mm, item.width_mm, item.height_mm) <= 0:
            issues.append(HardPrecheckIssue(
                "INVALID_DIMENSION", f"Item {item.item_id} has non-positive dimensions",
                (item.item_id,),
            ))
        if item.weight_kg < 0:
            issues.append(HardPrecheckIssue(
                "INVALID_WEIGHT", f"Item {item.item_id} has negative weight",
                (item.item_id,),
            ))
        orientations = provider.candidates(item)
        if not orientations:
            issues.append(HardPrecheckIssue(
                "NO_ALLOWED_ORIENTATION", f"Item {item.item_id} has no allowed orientation",
                (item.item_id,),
            ))
            compatible[item.item_id] = ()
            continue
        dimension_compatible = tuple(
            value.container_id
            for value in inventory.available_containers
            if _dimensions_fit(item, value, provider)
        )
        fully_compatible = tuple(
            value.container_id
            for value in inventory.available_containers
            if value.container_id in dimension_compatible
            and item.weight_kg <= value.max_weight_kg
        )
        compatible[item.item_id] = fully_compatible
        if not dimension_compatible:
            issues.append(HardPrecheckIssue(
                "ITEM_TOO_LARGE",
                f"Item {item.item_id} does not fit any available container orientation",
                (item.item_id,),
            ))
        elif not fully_compatible:
            issues.append(HardPrecheckIssue(
                "ITEM_TOO_HEAVY",
                f"Item {item.item_id} exceeds every dimension-compatible payload",
                (item.item_id,),
            ))

    total_item_volume = sum(value.volume_m3 for value in items)
    total_item_weight = sum(value.weight_kg for value in items)
    total_volume = sum(container_volume_m3(value) for value in inventory.available_containers)
    total_payload = sum(value.max_weight_kg for value in inventory.available_containers)
    if total_volume + 1e-12 < total_item_volume:
        issues.append(HardPrecheckIssue(
            "INSUFFICIENT_TOTAL_VOLUME",
            "Total available container volume is smaller than total item volume",
        ))
    if total_payload + 1e-9 < total_item_weight:
        issues.append(HardPrecheckIssue(
            "INSUFFICIENT_TOTAL_CAPACITY",
            "Total available container payload is smaller than total item weight",
        ))

    return HardPrecheckResult(
        valid=not issues,
        issues=tuple(issues),
        compatible_container_ids_by_item=compatible,
        total_item_volume_m3=total_item_volume,
        total_item_weight_kg=total_item_weight,
        total_inventory_volume_m3=total_volume,
        total_inventory_payload_kg=total_payload,
    )


def _finite_capacity_lower_bound(required: float, capacities: list[float]) -> int:
    if required <= 0:
        return 0
    accumulated = 0.0
    for count, capacity in enumerate(sorted(capacities, reverse=True), start=1):
        accumulated += capacity
        if accumulated + 1e-12 >= required:
            return count
    return len(capacities) + 1


def estimate_container_lower_bound(
    items: list[Item], inventory: NormalizedContainerInventory,
) -> LowerBoundEstimate:
    """Tính volume/payload lower bound trên physical inventory hữu hạn."""
    volume = _finite_capacity_lower_bound(
        sum(value.volume_m3 for value in items),
        [container_volume_m3(value) for value in inventory.available_containers],
    )
    payload = _finite_capacity_lower_bound(
        sum(value.weight_kg for value in items),
        [value.max_weight_kg for value in inventory.available_containers],
    )
    aggregate = max(volume, payload)
    return LowerBoundEstimate(
        volume_lower_bound=volume,
        payload_lower_bound=payload,
        aggregate_lower_bound=aggregate,
        inventory_physical_count=inventory.physical_container_count,
        attainable_by_aggregate_capacity=(
            aggregate <= inventory.physical_container_count
        ),
    )
