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


@dataclass(frozen=True)
class CapacityLimitAssessment:
    """Điều kiện cần theo số physical container tối đa của request.

    Volume và payload được đánh giá độc lập bằng các capacity lớn nhất trong
    inventory. Vì vậy một kết quả không hợp lệ là chứng minh chắc chắn; kết quả
    hợp lệ chỉ là precheck aggregate, không chứng minh khả thi hình học.
    """

    valid: bool
    max_used_container_count: int
    required_volume_m3: float
    attainable_volume_m3: float
    volume_deficit_m3: float
    required_payload_kg: float
    attainable_payload_kg: float
    payload_deficit_kg: float
    volume_lower_bound: int
    payload_lower_bound: int
    aggregate_lower_bound: int
    issues: tuple[HardPrecheckIssue, ...]

    def metadata(self) -> dict[str, object]:
        return {
            "capacity_limit_precheck_valid": self.valid,
            "capacity_limit_max_used_container_count": self.max_used_container_count,
            "capacity_limit_required_volume_m3": self.required_volume_m3,
            "capacity_limit_attainable_volume_m3": self.attainable_volume_m3,
            "capacity_limit_volume_deficit_m3": self.volume_deficit_m3,
            "capacity_limit_required_payload_kg": self.required_payload_kg,
            "capacity_limit_attainable_payload_kg": self.attainable_payload_kg,
            "capacity_limit_payload_deficit_kg": self.payload_deficit_kg,
            "capacity_limit_volume_lower_bound": self.volume_lower_bound,
            "capacity_limit_payload_lower_bound": self.payload_lower_bound,
            "capacity_limit_aggregate_lower_bound": self.aggregate_lower_bound,
            "capacity_limit_issue_count": len(self.issues),
            "capacity_limit_issues": [
                {
                    "code": issue.code,
                    "message": issue.message,
                    "item_ids": list(issue.item_ids),
                    "container_ids": list(issue.container_ids),
                }
                for issue in self.issues
            ],
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


def assess_capacity_within_container_limit(
    items: list[Item],
    inventory: NormalizedContainerInventory,
    max_used_container_count: int,
) -> CapacityLimitAssessment:
    """Chứng minh sớm request không đủ aggregate capacity trong giới hạn N."""
    if max_used_container_count <= 0:
        raise ValueError("max_used_container_count must be positive")
    if max_used_container_count > inventory.physical_container_count:
        raise ValueError(
            "max_used_container_count cannot exceed available physical inventory"
        )

    required_volume = sum(value.volume_m3 for value in items)
    required_payload = sum(value.weight_kg for value in items)
    volumes = sorted(
        (container_volume_m3(value) for value in inventory.available_containers),
        reverse=True,
    )
    payloads = sorted(
        (value.max_weight_kg for value in inventory.available_containers),
        reverse=True,
    )
    attainable_volume = sum(volumes[:max_used_container_count])
    attainable_payload = sum(payloads[:max_used_container_count])
    volume_deficit = max(0.0, required_volume - attainable_volume)
    payload_deficit = max(0.0, required_payload - attainable_payload)
    lower_bound = estimate_container_lower_bound(items, inventory)
    issues: list[HardPrecheckIssue] = []
    if volume_deficit > 1e-12:
        issues.append(HardPrecheckIssue(
            "INSUFFICIENT_VOLUME_WITHIN_CONTAINER_LIMIT",
            "Tổng thể tích của tối đa "
            f"{max_used_container_count} container lớn nhất vẫn thiếu "
            f"{volume_deficit:.6f} m³.",
        ))
    if payload_deficit > 1e-9:
        issues.append(HardPrecheckIssue(
            "INSUFFICIENT_PAYLOAD_WITHIN_CONTAINER_LIMIT",
            "Tổng tải trọng của tối đa "
            f"{max_used_container_count} container lớn nhất vẫn thiếu "
            f"{payload_deficit:.6f} kg.",
        ))
    return CapacityLimitAssessment(
        valid=not issues,
        max_used_container_count=max_used_container_count,
        required_volume_m3=required_volume,
        attainable_volume_m3=attainable_volume,
        volume_deficit_m3=volume_deficit,
        required_payload_kg=required_payload,
        attainable_payload_kg=attainable_payload,
        payload_deficit_kg=payload_deficit,
        volume_lower_bound=lower_bound.volume_lower_bound,
        payload_lower_bound=lower_bound.payload_lower_bound,
        aggregate_lower_bound=lower_bound.aggregate_lower_bound,
        issues=tuple(issues),
    )
