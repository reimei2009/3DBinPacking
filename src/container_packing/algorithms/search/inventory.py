"""Chuẩn hóa inventory container vật lý thành các nhóm type tương đương."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
import json

from ...schemas import Container


@dataclass(frozen=True)
class InventorySearchLimits:
    """Phân biệt inventory khả dụng với số container được phép sử dụng."""

    initial_used_container_count: int = 1
    max_used_container_count: int = 1
    automatically_increase_container_count: bool = False

    def __post_init__(self) -> None:
        if self.initial_used_container_count <= 0:
            raise ValueError("initial_used_container_count must be positive")
        if self.max_used_container_count <= 0:
            raise ValueError("max_used_container_count must be positive")
        if self.initial_used_container_count > self.max_used_container_count:
            raise ValueError(
                "initial_used_container_count cannot exceed max_used_container_count"
            )

    @property
    def cardinalities(self) -> tuple[int, ...]:
        if not self.automatically_increase_container_count:
            return (self.initial_used_container_count,)
        return tuple(range(
            self.initial_used_container_count,
            self.max_used_container_count + 1,
        ))


@dataclass(frozen=True)
class ContainerTypeGroup:
    """Các physical container có cùng geometry, payload, cost và profile."""

    type_id: str
    physical_containers: tuple[Container, ...]
    constraint_profile: str

    @property
    def representative(self) -> Container:
        return self.physical_containers[0]

    @property
    def quantity(self) -> int:
        return len(self.physical_containers)

    @property
    def physical_container_ids(self) -> tuple[str, ...]:
        return tuple(value.container_id for value in self.physical_containers)


@dataclass(frozen=True)
class NormalizedContainerInventory:
    """Inventory khả dụng đã được kiểm tra ID và nhóm type deterministic."""

    available_containers: tuple[Container, ...]
    groups: tuple[ContainerTypeGroup, ...]
    unavailable_container_ids: tuple[str, ...]

    @property
    def physical_container_count(self) -> int:
        return len(self.available_containers)

    @property
    def equivalent_type_count(self) -> int:
        return len(self.groups)

    @property
    def by_container_id(self) -> dict[str, Container]:
        return {value.container_id: value for value in self.available_containers}

    @property
    def type_id_by_container_id(self) -> dict[str, str]:
        return {
            container.container_id: group.type_id
            for group in self.groups
            for container in group.physical_containers
        }

    def metadata(self) -> dict[str, object]:
        return {
            "inventory_physical_container_count": self.physical_container_count,
            "inventory_equivalent_type_count": self.equivalent_type_count,
            "inventory_unavailable_container_count": len(self.unavailable_container_ids),
            "inventory_container_types": [
                {
                    "type_id": group.type_id,
                    "quantity": group.quantity,
                    "representative_container_id": group.representative.container_id,
                    "constraint_profile": group.constraint_profile,
                }
                for group in self.groups
            ],
        }


def _constraint_profile(container: Container) -> str:
    value = container.source.get(
        "constraint_profile_id",
        container.source.get("constraint_profile", "default"),
    )
    return str(value)


def _volume_m3(container: Container) -> float:
    return (
        container.length_mm * container.width_mm * container.height_mm
        / 1_000_000_000.0
    )


def _type_key(container: Container) -> tuple[float | str, ...]:
    return (
        float(container.length_mm),
        float(container.width_mm),
        float(container.height_mm),
        float(container.max_weight_kg),
        float(container.cost),
        _constraint_profile(container),
    )


def _type_id(key: tuple[float | str, ...]) -> str:
    payload = json.dumps(key, separators=(",", ":"), ensure_ascii=True)
    return "CT-" + sha256(payload.encode("utf-8")).hexdigest()[:12].upper()


def normalize_container_inventory(
    containers: list[Container],
) -> NormalizedContainerInventory:
    """Lọc container unavailable và nhóm các physical instance tương đương."""
    ids = [value.container_id for value in containers]
    duplicates = sorted(value for value, count in Counter(ids).items() if count > 1)
    if duplicates:
        raise ValueError("Duplicate container IDs: " + ", ".join(duplicates))

    available = tuple(sorted(
        (value for value in containers if value.availability > 0),
        key=lambda value: value.container_id,
    ))
    unavailable = tuple(sorted(
        value.container_id for value in containers if value.availability <= 0
    ))
    if not available:
        raise ValueError("Container inventory has no available physical instance")

    grouped: dict[tuple[float | str, ...], list[Container]] = {}
    for container in available:
        if min(
            container.length_mm,
            container.width_mm,
            container.height_mm,
            container.max_weight_kg,
            container.cost,
        ) <= 0:
            raise ValueError(
                f"Container {container.container_id} has non-positive geometry, payload, or cost"
            )
        grouped.setdefault(_type_key(container), []).append(container)

    groups = tuple(sorted(
        (
            ContainerTypeGroup(
                type_id=_type_id(key),
                physical_containers=tuple(sorted(values, key=lambda value: value.container_id)),
                constraint_profile=str(key[-1]),
            )
            for key, values in grouped.items()
        ),
        key=lambda value: (
            value.representative.cost,
            _volume_m3(value.representative),
            value.type_id,
        ),
    ))
    return NormalizedContainerInventory(available, groups, unavailable)
