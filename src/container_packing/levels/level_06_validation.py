"""Independent validator for the explicit Level 6 nesting relation contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..schemas import Item, Placement, ValidationIssue, ValidationResult
from .nesting import NestingAttributes, attributes_for_item
from .nesting_engine import (
    NestingEvaluationError,
    NestingRecord,
    NestingRelation,
    evaluate_nesting,
)


@dataclass(frozen=True)
class Level06NestingValidation:
    result: ValidationResult
    records: tuple[NestingRecord, ...]
    relations: tuple[NestingRelation, ...]

    def payload(self) -> dict[str, Any]:
        return {
            "valid": self.result.valid,
            "model": "explicit_nesting_chain_effective_height_v1",
            "records": [value.to_dict() for value in self.records],
            "relations": [value.to_dict() for value in self.relations],
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


def validate_nesting(
    items: list[Item],
    placements: list[Placement],
    relations: list[NestingRelation],
    *,
    clearance_mm: float = 0.0,
) -> Level06NestingValidation:
    """Recompute graph and effective height using only canonical source data.

    This validator is deliberately independent of the future solver and does
    not make an overlapping placement geometrically feasible.  It validates
    only declared Level 6 nesting semantics for this checkpoint.
    """
    if clearance_mm < 0:
        raise ValueError("Nesting clearance_mm must be non-negative")
    issues: list[ValidationIssue] = []
    item_by_id: dict[str, Item] = {}
    for item in items:
        if not item.item_id or not item.item_id.strip():
            issues.append(ValidationIssue("EMPTY_NESTING_ITEM_ID", "Nesting input contains an empty item ID"))
            continue
        if item.item_id in item_by_id:
            issues.append(ValidationIssue(
                "DUPLICATE_NESTING_ITEM", f"Item {item.item_id} appears more than once in nesting input", (item.item_id,)
            ))
            continue
        item_by_id[item.item_id] = item
    placement_ids = [value.item_id for value in placements]
    for item_id in sorted({value for value in placement_ids if placement_ids.count(value) > 1}):
        issues.append(ValidationIssue(
            "DUPLICATE_NESTING_PLACEMENT", f"Item {item_id} appears more than once in nesting placements", (item_id,)
        ))
    unknown = sorted(set(placement_ids) - set(item_by_id))
    missing = sorted(set(item_by_id) - set(placement_ids))
    for item_id in unknown:
        issues.append(ValidationIssue(
            "UNKNOWN_NESTING_ITEM", f"Nesting placement references unknown item {item_id}", (item_id,)
        ))
    for item_id in missing:
        issues.append(ValidationIssue(
            "MISSING_NESTING_PLACEMENT", f"Required item {item_id} has no nesting placement", (item_id,)
        ))
    if issues:
        return Level06NestingValidation(ValidationResult(False, issues), (), ())

    try:
        attributes: dict[str, NestingAttributes] = {
            item_id: attributes_for_item(item) for item_id, item in item_by_id.items()
        }
        evaluation = evaluate_nesting(placements, attributes, relations, clearance_mm=clearance_mm)
    except (ValueError, NestingEvaluationError) as exc:
        issues.append(ValidationIssue("NESTING_RELATION_INVALID", str(exc)))
        return Level06NestingValidation(ValidationResult(False, issues), (), ())
    return Level06NestingValidation(
        ValidationResult(True, ()), evaluation.records, evaluation.relations
    )
