"""Independent Level 8 static LIFO/unloadability validator."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from ..schemas import Item, Placement, ValidationIssue, ValidationResult
from .unloading import UnloadingAccessibility, UnloadingSettings, assess_unloading_accessibility


@dataclass(frozen=True)
class Level08UnloadingValidation:
    result: ValidationResult
    records: tuple[UnloadingAccessibility, ...]
    settings: UnloadingSettings | None

    def accessibility_rows(self) -> list[dict[str, Any]]:
        return [record.to_dict() for record in self.records]

    def rehandle_rows(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for record in self.records:
            for rank, blocker_item_id in enumerate(record.later_priority_blocker_ids, start=1):
                rows.append({
                    "target_item_id": record.item_id,
                    "container_id": record.container_id,
                    "target_delivery_priority": record.delivery_priority,
                    "blocker_item_id": blocker_item_id,
                    "blocker_relation": "later_delivery_priority_direct_path_blocker",
                    "rehandle_rank": rank,
                    "counting_model": "direct_later_priority_blockers_v1",
                })
        return rows

    def payload(self) -> dict[str, Any]:
        return {
            "valid": self.result.valid,
            "model": "straight_path_static_lifo_v1",
            "settings": None if self.settings is None else {
                "door_face": self.settings.door_face,
                "path_clearance_mm": self.settings.path_clearance_mm,
                "delivery_priority_direction": self.settings.delivery_priority_direction,
                "rehandle_count_mode": self.settings.rehandle_count_mode,
                "profile_source": self.settings.profile_source,
            },
            "records": self.accessibility_rows(),
            "rehandle_plan": self.rehandle_rows(),
            "violations": [
                {"code": issue.code, "message": issue.message, "item_ids": list(issue.item_ids), "container_id": issue.container_id}
                for issue in self.result.issues
            ],
        }


def validate_unloading_lifo(
    items: Iterable[Item],
    placements: Iterable[Placement],
    unloading_config: dict[str, Any],
    *,
    tolerance_mm: float = 1e-6,
) -> Level08UnloadingValidation:
    """Recompute static LIFO evidence from source metadata and final placements.

    This intentionally does not call a packing solver or a previous-level
    validator. A future composed Level 8 validator will append it after the
    inherited geometry/support/stack/load/balance validation bundle.
    """
    issues: list[ValidationIssue] = []
    item_list = list(items)
    placement_list = list(placements)
    item_ids = [item.item_id for item in item_list]
    placement_ids = [placement.item_id for placement in placement_list]
    for item_id in sorted({value for value in item_ids if item_ids.count(value) > 1}):
        issues.append(ValidationIssue("DUPLICATE_UNLOADING_ITEM", f"Item {item_id} appears more than once in unloading input", (item_id,)))
    for item_id in sorted({value for value in placement_ids if placement_ids.count(value) > 1}):
        issues.append(ValidationIssue("DUPLICATE_UNLOADING_PLACEMENT", f"Item {item_id} appears more than once in unloading placements", (item_id,)))
    known = set(item_ids)
    for item_id in sorted(set(placement_ids) - known):
        issues.append(ValidationIssue("UNKNOWN_UNLOADING_ITEM", f"Unloading placement references unknown item {item_id}", (item_id,)))
    for item_id in sorted(known - set(placement_ids)):
        issues.append(ValidationIssue("MISSING_UNLOADING_ITEM", f"Required item {item_id} has no unloading placement", (item_id,)))
    if issues:
        return Level08UnloadingValidation(ValidationResult(False, issues), (), None)
    try:
        settings = UnloadingSettings.from_config(unloading_config)
        records = assess_unloading_accessibility(item_list, placement_list, settings, tolerance_mm=tolerance_mm)
    except ValueError as exc:
        return Level08UnloadingValidation(
            ValidationResult(False, [ValidationIssue("UNLOADING_INPUT_INVALID", str(exc))]), (), None
        )
    for record in records:
        if record.later_priority_blocker_ids:
            issues.append(ValidationIssue(
                "LIFO_LATER_PRIORITY_BLOCKER",
                f"Item {record.item_id} delivery priority {record.delivery_priority} is blocked at {settings.door_face} by later delivery item(s): "
                + ", ".join(record.later_priority_blocker_ids),
                (record.item_id, *record.later_priority_blocker_ids),
                record.container_id,
            ))
    return Level08UnloadingValidation(ValidationResult(not issues, issues), records, settings)
