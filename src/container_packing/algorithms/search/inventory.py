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

    @property
    def declared_type_ids(self) -> tuple[str, ...]:
        """Các nhãn loại do nguồn dữ liệu khai báo, nếu có."""
        return tuple(sorted({
            str(value.source["container_type_id"])
            for value in self.physical_containers
            if value.source.get("container_type_id") not in {None, ""}
        }))

    @property
    def display_type_id(self) -> str:
        """Nhãn dễ đọc cho UI; không thay thế type tương đương canonical."""
        declared = self.declared_type_ids
        return " + ".join(declared) if declared else self.type_id


@dataclass(frozen=True)
class ContainerTypeComposition:
    """Một phương án số lượng theo loại, độc lập với physical container ID.

    Hai subset chỉ khác ID của các container tương đương vật lý phải có cùng
    signature. Physical IDs chỉ được materialize deterministic ngay trước khi
    constructive solver chạy.
    """

    quantities: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        if not self.quantities:
            raise ValueError("Container type composition cannot be empty")
        type_ids = [type_id for type_id, _ in self.quantities]
        if type_ids != sorted(type_ids) or len(type_ids) != len(set(type_ids)):
            raise ValueError("Container type composition must use unique sorted type IDs")
        if any(quantity <= 0 for _, quantity in self.quantities):
            raise ValueError("Container type composition quantities must be positive")

    @property
    def container_count(self) -> int:
        return sum(quantity for _, quantity in self.quantities)

    @property
    def signature(self) -> tuple[tuple[str, int], ...]:
        return self.quantities

    @classmethod
    def from_counts(cls, counts: dict[str, int]) -> "ContainerTypeComposition":
        return cls(tuple(sorted(
            (str(type_id), int(quantity))
            for type_id, quantity in counts.items()
            if int(quantity) > 0
        )))


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

    @property
    def groups_by_type_id(self) -> dict[str, ContainerTypeGroup]:
        return {group.type_id: group for group in self.groups}

    def materialize(
        self, composition: ContainerTypeComposition,
    ) -> tuple[Container, ...]:
        """Chọn physical IDs đầu tiên theo ID cho một composition hợp lệ."""
        groups = self.groups_by_type_id
        selected: list[Container] = []
        for type_id, quantity in composition.quantities:
            group = groups.get(type_id)
            if group is None:
                raise ValueError(f"Unknown container type in composition: {type_id}")
            if quantity > group.quantity:
                raise ValueError(
                    f"Composition requests {quantity} containers of {type_id}, "
                    f"but inventory contains only {group.quantity}"
                )
            selected.extend(group.physical_containers[:quantity])
        return tuple(sorted(selected, key=lambda value: value.container_id))

    @property
    def inventory_fingerprint(self) -> str:
        """Dấu vết deterministic của inventory physical đang khả dụng."""
        payload = [
            {
                "container_id": value.container_id,
                "declared_type_id": str(value.source.get("container_type_id", "")),
                "length_mm": value.length_mm,
                "width_mm": value.width_mm,
                "height_mm": value.height_mm,
                "max_weight_kg": value.max_weight_kg,
                "cost": value.cost,
                "constraint_profile": _constraint_profile(value),
            }
            for value in self.available_containers
        ]
        encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        return sha256(encoded.encode("utf-8")).hexdigest()

    def metadata(self) -> dict[str, object]:
        return {
            "inventory_physical_container_count": self.physical_container_count,
            "inventory_equivalent_type_count": self.equivalent_type_count,
            "inventory_unavailable_container_count": len(self.unavailable_container_ids),
            "inventory_fingerprint": self.inventory_fingerprint,
            "inventory_container_types": [
                {
                    "type_id": group.type_id,
                    "equivalent_type_id": group.type_id,
                    "declared_type_ids": list(group.declared_type_ids),
                    "display_type_id": group.display_type_id,
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
