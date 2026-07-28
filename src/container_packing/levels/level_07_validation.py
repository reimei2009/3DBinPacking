"""Independent Level 7 center-of-mass and balance validator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..schemas import Container, Item, Placement, ValidationIssue, ValidationResult
from .center_of_mass import CenterOfMassError, CenterOfMassRecord, evaluate_center_of_mass


@dataclass(frozen=True)
class Level07BalanceValidation:
    result: ValidationResult
    records: tuple[CenterOfMassRecord, ...]

    def payload(self) -> dict[str, Any]:
        return {
            "valid": self.result.valid,
            "model": "mass_weighted_item_geometric_center_v1",
            "records": [value.to_dict() for value in self.records],
            "violations": [
                {"code": value.code, "message": value.message, "item_ids": list(value.item_ids), "container_id": value.container_id}
                for value in self.result.issues
            ],
        }


def validate_container_balance(
    items: list[Item] | tuple[Item, ...],
    containers: list[Container] | tuple[Container, ...],
    placements: list[Placement] | tuple[Placement, ...],
    balance_config: dict[str, Any],
    *,
    weight_tolerance_kg: float = 1e-6,
    balance_tolerance: float = 1e-9,
) -> Level07BalanceValidation:
    """Recompute COG and balance from source items and canonical placements."""
    if weight_tolerance_kg < 0:
        raise ValueError("weight_tolerance_kg must be non-negative")
    issues: list[ValidationIssue] = []
    item_by_id = _items_by_id(items, issues)
    container_ids = {value.container_id for value in containers}
    placement_ids = [value.item_id for value in placements]
    for item_id in sorted({value for value in placement_ids if placement_ids.count(value) > 1}):
        issues.append(ValidationIssue("DUPLICATE_BALANCE_PLACEMENT", f"Item {item_id} appears more than once in balance placements", (item_id,)))
    for item_id in sorted(set(placement_ids) - set(item_by_id)):
        issues.append(ValidationIssue("UNKNOWN_BALANCE_ITEM", f"Balance placement references unknown item {item_id}", (item_id,)))
    for item_id in sorted(set(item_by_id) - set(placement_ids)):
        issues.append(ValidationIssue("MISSING_BALANCE_ITEM", f"Required item {item_id} has no balance placement", (item_id,)))
    for placement in placements:
        item = item_by_id.get(placement.item_id)
        if placement.container_id not in container_ids:
            issues.append(ValidationIssue("UNKNOWN_BALANCE_CONTAINER", f"Balance placement references unknown container {placement.container_id}", (placement.item_id,), placement.container_id))
        if item is not None and abs(placement.weight_kg - item.weight_kg) > weight_tolerance_kg:
            issues.append(ValidationIssue("BALANCE_WEIGHT_MISMATCH", f"Item {placement.item_id} placement weight={placement.weight_kg} kg but source weight={item.weight_kg} kg", (placement.item_id,), placement.container_id))
    if issues:
        return Level07BalanceValidation(ValidationResult(False, issues), ())
    try:
        evaluation = evaluate_center_of_mass(placements, containers, balance_config, tolerance=balance_tolerance)
    except (ValueError, CenterOfMassError) as exc:
        return Level07BalanceValidation(ValidationResult(False, [ValidationIssue("BALANCE_INPUT_INVALID", str(exc))]), ())
    for record in evaluation.records:
        if not record.longitudinal_balanced:
            issues.append(ValidationIssue("LONGITUDINAL_CENTER_OF_MASS_OUT_OF_BAND", f"Container {record.container_id} longitudinal COG offset {record.absolute_longitudinal_offset_ratio} exceeds {record.max_longitudinal_offset_ratio}", container_id=record.container_id))
        if not record.lateral_balanced:
            issues.append(ValidationIssue("LATERAL_CENTER_OF_MASS_OUT_OF_BAND", f"Container {record.container_id} lateral COG offset {record.absolute_lateral_offset_ratio} exceeds {record.max_lateral_offset_ratio}", container_id=record.container_id))
    return Level07BalanceValidation(ValidationResult(not issues, issues), evaluation.records)


def _items_by_id(items: list[Item] | tuple[Item, ...], issues: list[ValidationIssue]) -> dict[str, Item]:
    item_by_id: dict[str, Item] = {}
    for item in items:
        item_id = item.item_id.strip()
        if not item_id:
            issues.append(ValidationIssue("EMPTY_BALANCE_ITEM_ID", "Balance input contains an empty item ID"))
        elif item_id in item_by_id:
            issues.append(ValidationIssue("DUPLICATE_BALANCE_ITEM", f"Item {item_id} appears more than once in balance input", (item_id,)))
        else:
            item_by_id[item_id] = item
    return item_by_id
