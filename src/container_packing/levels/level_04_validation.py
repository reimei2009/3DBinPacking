"""Independent Level 4 stack-graph validation over the Level 3 contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..schemas import Container, Item, Placement, ValidationIssue, ValidationResult
from .level_03_validation import validate_solution as validate_level3_solution
from .stackability import (
    StackParentRelation,
    StackRecord,
    StackabilitySettings,
    attributes_for_item,
)


@dataclass(frozen=True)
class Level04Validation:
    result: ValidationResult
    support_validation: Any
    stack_records: tuple[StackRecord, ...]

    def payload(self) -> dict[str, Any]:
        return {
            "valid": self.result.valid,
            "support": self.support_validation.payload(),
            "stacks": [record.to_dict() for record in self.stack_records],
        }


def validate_solution(
    items: list[Item],
    containers: list[Container],
    placements: list[Placement],
    parent_relations: list[StackParentRelation],
    stackability_config: dict[str, Any],
    *,
    support_threshold: float = 0.8,
    support_epsilon_mm: float = 1e-4,
    coordinate_tolerance: float = 1e-4,
    weight_tolerance: float = 1e-6,
) -> Level04Validation:
    """Validate stack declarations independently of any future Level 4 solver."""
    settings = StackabilitySettings.from_config(stackability_config)
    support = validate_level3_solution(
        items,
        containers,
        placements,
        support_threshold=support_threshold,
        support_epsilon_mm=support_epsilon_mm,
        coordinate_tolerance=coordinate_tolerance,
        weight_tolerance=weight_tolerance,
    )
    issues = list(support.result.issues)
    attributes = {item.item_id: attributes_for_item(item, settings) for item in items}
    placement_by_id = {placement.item_id: placement for placement in placements}
    support_by_item = {record.item_id: record for record in support.support_records}
    parents: dict[str, StackParentRelation] = {}

    for relation in parent_relations:
        parent = placement_by_id.get(relation.parent_item_id)
        child = placement_by_id.get(relation.child_item_id)
        if parent is None or child is None:
            issues.append(ValidationIssue(
                "UNKNOWN_STACK_RELATION_ITEM",
                f"Stack relation {relation.parent_item_id}->{relation.child_item_id} references an unknown placement",
                (relation.parent_item_id, relation.child_item_id), relation.container_id,
            ))
            continue
        if relation.parent_item_id == relation.child_item_id:
            issues.append(ValidationIssue(
                "SELF_STACK_PARENT", f"Item {child.item_id} cannot be its own stack parent",
                (child.item_id,), relation.container_id,
            ))
            continue
        if child.item_id in parents:
            issues.append(ValidationIssue(
                "MULTIPLE_DECLARED_STACK_PARENTS",
                f"Item {child.item_id} has more than one declared direct stack parent",
                (parents[child.item_id].parent_item_id, relation.parent_item_id, child.item_id), relation.container_id,
            ))
            continue
        parents[child.item_id] = relation
        _validate_relation(
            relation, parent, child, attributes, support_by_item, issues, support_epsilon_mm,
        )

    for item_id, placement in placement_by_id.items():
        relation = parents.get(item_id)
        if abs(placement.z_mm) <= support_epsilon_mm and relation is not None:
            issues.append(ValidationIssue(
                "FLOOR_ITEM_HAS_STACK_PARENT", f"Floor item {item_id} must be a stack root", (item_id,), placement.container_id,
            ))
        if abs(placement.z_mm) > support_epsilon_mm and relation is None:
            issues.append(ValidationIssue(
                "MISSING_DECLARED_STACK_PARENT",
                f"Non-floor item {item_id} requires one declared stack parent", (item_id,), placement.container_id,
            ))
        if attributes[item_id].is_non_stackable and (relation is not None or any(
            value.parent_item_id == item_id for value in parents.values()
        )):
            issues.append(ValidationIssue(
                "NON_STACKABLE_ITEM_IN_STACK",
                f"Non-stackable item {item_id} must be a floor root with no children", (item_id,), placement.container_id,
            ))

    _append_cycle_issues(parents, issues)
    records = _stack_records(placement_by_id, parents, attributes, issues)
    return Level04Validation(ValidationResult(valid=not issues, issues=issues), support, tuple(records))


def _validate_relation(relation, parent, child, attributes, support_by_item, issues, epsilon: float) -> None:
    if relation.container_id != parent.container_id or relation.container_id != child.container_id:
        issues.append(ValidationIssue(
            "STACK_PARENT_CONTAINER_MISMATCH",
            f"Declared stack relation {parent.item_id}->{child.item_id} is not in one container",
            (parent.item_id, child.item_id), relation.container_id,
        ))
    if attributes[parent.item_id].stack_group_id != attributes[child.item_id].stack_group_id:
        issues.append(ValidationIssue(
            "INCOMPATIBLE_STACKABILITY_CODE",
            f"Items {parent.item_id} and {child.item_id} have different stackability codes",
            (parent.item_id, child.item_id), child.container_id,
        ))
    if abs(child.z_mm - (parent.z_mm + parent.height_mm)) > epsilon:
        issues.append(ValidationIssue(
            "STACK_PARENT_NOT_TOP_CONTACT",
            f"Declared parent {parent.item_id} is not at the top-contact height of {child.item_id}",
            (parent.item_id, child.item_id), child.container_id,
        ))
    support_record = support_by_item.get(child.item_id)
    if support_record is None or parent.item_id not in support_record.supporting_item_ids:
        issues.append(ValidationIssue(
            "DECLARED_PARENT_NOT_GEOMETRIC_SUPPORTER",
            f"Declared parent {parent.item_id} does not geometrically support {child.item_id}",
            (parent.item_id, child.item_id), child.container_id,
        ))


def _append_cycle_issues(parents: dict[str, StackParentRelation], issues: list[ValidationIssue]) -> None:
    for child_id in parents:
        seen: set[str] = set()
        current = child_id
        while current in parents:
            if current in seen:
                issues.append(ValidationIssue(
                    "STACK_PARENT_CYCLE", f"Stack parent cycle includes {current}", tuple(sorted(seen)), None,
                ))
                break
            seen.add(current)
            current = parents[current].parent_item_id


def _stack_records(placements, parents, attributes, issues) -> list[StackRecord]:
    records: list[StackRecord] = []
    children: dict[str, list[str]] = {}
    for child_id, relation in parents.items():
        children.setdefault(relation.parent_item_id, []).append(child_id)
    for item_id, placement in placements.items():
        chain = _root_to_item_chain(item_id, parents)
        if chain is None:
            records.append(StackRecord(item_id, placement.container_id, None, None, None, None, None))
            continue
        root_id = chain[0]
        subtree_layers = _maximum_subtree_layers(root_id, children)
        effective_cap = min(attributes[value].max_stack_layers for value in chain)
        if len(chain) > effective_cap:
            issues.append(ValidationIssue(
                "STACK_LAYER_LIMIT_EXCEEDED",
                f"Stack chain ending at {item_id} has {len(chain)} layers but cap is {effective_cap}",
                tuple(chain), placement.container_id,
            ))
        records.append(StackRecord(
            item_id, placement.container_id, parents[item_id].parent_item_id if item_id in parents else None,
            f"{placement.container_id}::{root_id}", len(chain) - 1, subtree_layers, effective_cap,
        ))
    return records


def _root_to_item_chain(item_id: str, parents: dict[str, StackParentRelation]) -> list[str] | None:
    chain = [item_id]
    seen = {item_id}
    current = item_id
    while current in parents:
        current = parents[current].parent_item_id
        if current in seen:
            return None
        seen.add(current)
        chain.append(current)
    return list(reversed(chain))


def _maximum_subtree_layers(item_id: str, children: dict[str, list[str]]) -> int:
    descendants = children.get(item_id, [])
    return 1 if not descendants else 1 + max(_maximum_subtree_layers(child, children) for child in descendants)
