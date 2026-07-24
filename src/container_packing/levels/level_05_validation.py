"""Independent Level 5 static load-bearing validator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..schemas import Item, Placement, ValidationIssue, ValidationResult
from .load_bearing import resolve_load_bearing_attributes
from .load_transfer import (
    LoadBearingRecord,
    LoadTransferEdge,
    LoadTransferError,
    evaluate_load_transfer,
)


@dataclass(frozen=True)
class Level05LoadValidation:
    result: ValidationResult
    records: tuple[LoadBearingRecord, ...]
    edges: tuple[LoadTransferEdge, ...]

    def payload(self) -> dict[str, Any]:
        return {
            "valid": self.result.valid,
            "model": "static_vertical_contact_area_recursive_v1",
            "records": [value.to_dict() for value in self.records],
            "edges": [value.to_dict() for value in self.edges],
            "violations": [
                {
                    "code": value.code,
                    "message": value.message,
                    "item_ids": list(value.item_ids),
                    "container_id": value.container_id,
                }
                for value in self.result.issues
            ],
        }


def validate_load_bearing(
    items: list[Item],
    placements: list[Placement],
    load_bearing_config: dict[str, Any],
    *,
    epsilon_mm: float = 1e-4,
    load_tolerance_kg: float = 1e-6,
) -> Level05LoadValidation:
    """Recompute strength attributes and load transfer without solver state."""
    if epsilon_mm <= 0:
        raise ValueError("epsilon_mm must be positive")
    if load_tolerance_kg < 0:
        raise ValueError("load_tolerance_kg must be non-negative")
    issues: list[ValidationIssue] = []
    item_ids = [value.item_id for value in items]
    placement_ids = [value.item_id for value in placements]
    duplicate_placements = sorted({
        value for value in placement_ids if placement_ids.count(value) > 1
    })
    item_by_id = {value.item_id: value for value in items}
    unknown = sorted(set(placement_ids) - set(item_ids))
    missing = sorted(set(item_ids) - set(placement_ids))
    for item_id in duplicate_placements:
        issues.append(ValidationIssue(
            "DUPLICATE_LOAD_PLACEMENT",
            f"Item {item_id} appears more than once in the load-bearing input",
            (item_id,),
        ))
    for item_id in unknown:
        issues.append(ValidationIssue(
            "UNKNOWN_LOAD_ITEM",
            f"Load-bearing placement references unknown item {item_id}",
            (item_id,),
        ))
    for item_id in missing:
        issues.append(ValidationIssue(
            "MISSING_LOAD_ITEM",
            f"Required item {item_id} has no load-bearing placement",
            (item_id,),
        ))
    for placement in placements:
        item = item_by_id.get(placement.item_id)
        if item is not None and abs(placement.weight_kg - item.weight_kg) > load_tolerance_kg:
            issues.append(ValidationIssue(
                "LOAD_WEIGHT_MISMATCH",
                f"Item {placement.item_id} placement weight={placement.weight_kg} kg "
                f"but source weight={item.weight_kg} kg",
                (placement.item_id,), placement.container_id,
            ))
    if issues:
        return Level05LoadValidation(ValidationResult(False, issues), (), ())

    try:
        attributes = resolve_load_bearing_attributes(items, load_bearing_config)
        evaluation = evaluate_load_transfer(
            placements, attributes, epsilon_mm=epsilon_mm
        )
    except (ValueError, LoadTransferError) as exc:
        issues.append(ValidationIssue("LOAD_GRAPH_INVALID", str(exc)))
        return Level05LoadValidation(ValidationResult(False, issues), (), ())

    incoming_by_supporter: dict[str, float] = {}
    outgoing_by_child: dict[str, list[LoadTransferEdge]] = {}
    for edge in evaluation.edges:
        incoming_by_supporter[edge.supporter_item_id] = (
            incoming_by_supporter.get(edge.supporter_item_id, 0.0)
            + edge.transferred_load_kg
        )
        outgoing_by_child.setdefault(edge.child_item_id, []).append(edge)
    placement_by_id = {value.item_id: value for value in placements}
    record_by_id = {value.item_id: value for value in evaluation.records}

    for item_id, record in record_by_id.items():
        incoming = incoming_by_supporter.get(item_id, 0.0)
        if abs(incoming - record.load_above_kg) > load_tolerance_kg:
            issues.append(ValidationIssue(
                "LOAD_CONSERVATION_MISMATCH",
                f"Item {item_id} load_above={record.load_above_kg} but incoming transfer={incoming}",
                (item_id,), record.container_id,
            ))
        placement = placement_by_id[item_id]
        outgoing = outgoing_by_child.get(item_id, [])
        if abs(placement.z_mm) > epsilon_mm:
            fraction_sum = sum(value.transfer_fraction for value in outgoing)
            transfer_sum = sum(value.transferred_load_kg for value in outgoing)
            if abs(fraction_sum - 1.0) > load_tolerance_kg:
                issues.append(ValidationIssue(
                    "LOAD_TRANSFER_FRACTION_MISMATCH",
                    f"Non-floor item {item_id} has transfer fractions summing to {fraction_sum}",
                    (item_id,), record.container_id,
                ))
            if abs(transfer_sum - record.total_transmitted_load_kg) > load_tolerance_kg:
                issues.append(ValidationIssue(
                    "LOAD_TRANSFER_TOTAL_MISMATCH",
                    f"Item {item_id} transfers {transfer_sum} but total load is {record.total_transmitted_load_kg}",
                    (item_id,), record.container_id,
                ))
        if record.load_above_kg > record.max_supported_weight_kg + load_tolerance_kg:
            issues.append(ValidationIssue(
                "LOAD_CAPACITY_EXCEEDED",
                f"Item {item_id} carries {record.load_above_kg} kg above capacity "
                f"{record.max_supported_weight_kg} kg",
                (item_id,), record.container_id,
            ))
        if record.is_fragile and record.load_above_kg > load_tolerance_kg:
            issues.append(ValidationIssue(
                "FRAGILE_ITEM_CARRYING_LOAD",
                f"Fragile item {item_id} carries {record.load_above_kg} kg",
                (item_id,), record.container_id,
            ))
    containers = sorted({value.container_id for value in placements})
    for container_id in containers:
        container_records = [
            value for value in evaluation.records if value.container_id == container_id
        ]
        own_weight = sum(value.own_weight_kg for value in container_records)
        floor_load = sum(
            record_by_id[value.item_id].total_transmitted_load_kg
            for value in placements
            if value.container_id == container_id and abs(value.z_mm) <= epsilon_mm
        )
        if abs(own_weight - floor_load) > load_tolerance_kg:
            issues.append(ValidationIssue(
                "CONTAINER_LOAD_CONSERVATION_MISMATCH",
                f"Container {container_id} has {own_weight} kg item weight but "
                f"{floor_load} kg reaches floor roots",
                tuple(sorted(value.item_id for value in container_records)),
                container_id,
            ))
    return Level05LoadValidation(
        ValidationResult(not issues, issues),
        evaluation.records,
        evaluation.edges,
    )
