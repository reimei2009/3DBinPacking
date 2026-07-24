"""Pure recursive vertical-load transfer over geometric contact areas."""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose

from ..geometry.support import contact_rectangle
from ..schemas import Placement
from .load_bearing import LoadBearingAttributes


class LoadTransferError(ValueError):
    """Raised when placements cannot form a valid vertical load graph."""


@dataclass(frozen=True)
class LoadTransferEdge:
    supporter_item_id: str
    child_item_id: str
    container_id: str
    contact_area_mm2: float
    transfer_fraction: float
    child_total_transmitted_load_kg: float
    transferred_load_kg: float

    def to_dict(self) -> dict[str, object]:
        return {
            "supporter_item_id": self.supporter_item_id,
            "child_item_id": self.child_item_id,
            "container_id": self.container_id,
            "contact_area_mm2": self.contact_area_mm2,
            "transfer_fraction": self.transfer_fraction,
            "child_total_transmitted_load_kg": self.child_total_transmitted_load_kg,
            "transferred_load_kg": self.transferred_load_kg,
        }


@dataclass(frozen=True)
class LoadBearingRecord:
    item_id: str
    container_id: str
    own_weight_kg: float
    load_above_kg: float
    total_transmitted_load_kg: float
    max_supported_weight_kg: float
    load_utilization_ratio: float | None
    safety_margin_kg: float
    is_fragile: bool
    load_capacity_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "item_id": self.item_id,
            "container_id": self.container_id,
            "own_weight_kg": self.own_weight_kg,
            "load_above_kg": self.load_above_kg,
            "total_transmitted_load_kg": self.total_transmitted_load_kg,
            "max_supported_weight_kg": self.max_supported_weight_kg,
            "load_utilization_ratio": self.load_utilization_ratio,
            "safety_margin_kg": self.safety_margin_kg,
            "is_fragile": self.is_fragile,
            "load_capacity_source": self.load_capacity_source,
        }


@dataclass(frozen=True)
class LoadTransferEvaluation:
    records: tuple[LoadBearingRecord, ...]
    edges: tuple[LoadTransferEdge, ...]


def evaluate_load_transfer(
    placements: list[Placement] | tuple[Placement, ...],
    attributes: dict[str, LoadBearingAttributes],
    *,
    epsilon_mm: float,
) -> LoadTransferEvaluation:
    """Distribute each item's accumulated load over all top-face contacts.

    Placements are processed from top to bottom. A child transfers its own
    weight plus every load already received from descendants. Fractions are
    normalized by individual positive contact areas.
    """
    if epsilon_mm <= 0:
        raise ValueError("epsilon_mm must be positive")
    placement_by_id: dict[str, Placement] = {}
    for placement in placements:
        if placement.item_id in placement_by_id:
            raise LoadTransferError(f"Duplicate placement item ID: {placement.item_id}")
        if placement.item_id not in attributes:
            raise LoadTransferError(
                f"Missing load-bearing attributes for item {placement.item_id}"
            )
        placement_by_id[placement.item_id] = placement

    support_specs: dict[str, tuple[tuple[Placement, float, float], ...]] = {}
    for child in placements:
        if abs(child.z_mm) <= epsilon_mm:
            support_specs[child.item_id] = ()
            continue
        contacts: list[tuple[Placement, float]] = []
        for supporter in placements:
            if supporter.item_id == child.item_id or supporter.container_id != child.container_id:
                continue
            if abs(child.z_mm - (supporter.z_mm + supporter.height_mm)) > epsilon_mm:
                continue
            rectangle = contact_rectangle(child, supporter)
            if rectangle is None:
                continue
            area = (rectangle[2] - rectangle[0]) * (rectangle[3] - rectangle[1])
            if area > 0:
                contacts.append((supporter, area))
        total_area = sum(area for _, area in contacts)
        if total_area <= 0:
            raise LoadTransferError(
                f"Non-floor item {child.item_id} has no positive-area load supporter"
            )
        support_specs[child.item_id] = tuple(
            (supporter, area, area / total_area)
            for supporter, area in sorted(contacts, key=lambda value: value[0].item_id)
        )

    total_load = {value.item_id: float(value.weight_kg) for value in placements}
    edges: list[LoadTransferEdge] = []
    ordered = sorted(placements, key=lambda value: (-value.z_mm, value.item_id))
    for child in ordered:
        child_total = total_load[child.item_id]
        for supporter, area, fraction in support_specs[child.item_id]:
            transferred = fraction * child_total
            total_load[supporter.item_id] += transferred
            edges.append(
                LoadTransferEdge(
                    supporter.item_id,
                    child.item_id,
                    child.container_id,
                    area,
                    fraction,
                    child_total,
                    transferred,
                )
            )

    records: list[LoadBearingRecord] = []
    for placement in sorted(placements, key=lambda value: value.item_id):
        strength = attributes[placement.item_id]
        load_above = total_load[placement.item_id] - placement.weight_kg
        capacity = strength.max_supported_weight_kg
        utilization = (
            load_above / capacity
            if capacity > 0
            else 0.0 if isclose(load_above, 0.0, abs_tol=1e-12) else None
        )
        records.append(
            LoadBearingRecord(
                placement.item_id,
                placement.container_id,
                placement.weight_kg,
                load_above,
                total_load[placement.item_id],
                capacity,
                utilization,
                capacity - load_above,
                strength.is_fragile,
                strength.load_capacity_source,
            )
        )
    return LoadTransferEvaluation(
        tuple(records),
        tuple(sorted(edges, key=lambda value: (value.child_item_id, value.supporter_item_id))),
    )
