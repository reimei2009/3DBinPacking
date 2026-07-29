"""Pure dependency and replay validation for a future Level 8 simulator.

This is intentionally not an event executor. It evaluates a caller-provided
removal order against immutable final placements, then independently checks the
remaining static state after each removal.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from ..geometry.support import evaluate_support
from ..schemas import Container, Item, Placement, ValidationIssue, ValidationResult
from .level_01_validation import validate_solution as validate_geometry_solution
from .level_08_validation import validate_unloading_lifo
from .nesting_engine import NestingRelation
from .unloading import UnloadingSettings, assess_unloading_accessibility


StateValidator = Callable[[list[Item], list[Placement]], ValidationResult]


@dataclass(frozen=True)
class UnloadingDependency:
    """``predecessor`` must be removed before ``successor`` can be removed."""

    predecessor_item_id: str
    successor_item_id: str
    container_id: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {
            "predecessor_item_id": self.predecessor_item_id,
            "successor_item_id": self.successor_item_id,
            "container_id": self.container_id,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class SequentialUnloadingStep:
    sequence: int
    item_id: str
    accepted: bool
    remaining_item_count: int
    required_predecessor_ids: tuple[str, ...]
    issues: tuple[ValidationIssue, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "item_id": self.item_id,
            "accepted": self.accepted,
            "remaining_item_count": self.remaining_item_count,
            "required_predecessor_ids": list(self.required_predecessor_ids),
            "issues": [
                {"code": issue.code, "message": issue.message, "item_ids": list(issue.item_ids), "container_id": issue.container_id}
                for issue in self.issues
            ],
        }


@dataclass(frozen=True)
class SequentialUnloadingValidation:
    result: ValidationResult
    dependencies: tuple[UnloadingDependency, ...]
    steps: tuple[SequentialUnloadingStep, ...]

    def payload(self) -> dict[str, Any]:
        return {
            "valid": self.result.valid,
            "model": "dependency_graph_static_state_replay_v1",
            "dependencies": [value.to_dict() for value in self.dependencies],
            "steps": [value.to_dict() for value in self.steps],
            "violations": [
                {"code": issue.code, "message": issue.message, "item_ids": list(issue.item_ids), "container_id": issue.container_id}
                for issue in self.result.issues
            ],
        }


def build_unloading_dependency_graph(
    items: Iterable[Item],
    placements: Iterable[Placement],
    settings: UnloadingSettings,
    *,
    nesting_relations: Iterable[NestingRelation] = (),
    support_epsilon_mm: float = 1e-4,
) -> tuple[UnloadingDependency, ...]:
    """Build conservative precedence from door blockers, support, and nesting.

    A support edge is ``child -> supporter``: a lower item may not leave while
    an item still depends on it. A nesting edge is ``child -> host``. Later
    door blockers are retained as explicit edges but remain strict-LIFO errors.
    """
    item_list = list(items)
    placement_list = list(placements)
    known_ids = {item.item_id for item in item_list}
    by_container: dict[str, list[Placement]] = defaultdict(list)
    for placement in placement_list:
        by_container[placement.container_id].append(placement)
    dependencies: set[UnloadingDependency] = set()

    for record in assess_unloading_accessibility(item_list, placement_list, settings):
        for blocker_id in record.later_priority_blocker_ids:
            dependencies.add(UnloadingDependency(
                blocker_id, record.item_id, record.container_id, "later_delivery_door_blocker"
            ))
    for placement in placement_list:
        support = evaluate_support(placement, by_container[placement.container_id], epsilon_mm=support_epsilon_mm)
        for supporter_id in support.supporting_item_ids:
            dependencies.add(UnloadingDependency(
                placement.item_id, supporter_id, placement.container_id, "external_support_before_supporter_removal"
            ))

    by_placement = {placement.item_id: placement for placement in placement_list}
    for relation in nesting_relations:
        if relation.host_item_id not in known_ids or relation.child_item_id not in known_ids:
            raise ValueError("Nesting dependency references item absent from sequential input")
        host = by_placement.get(relation.host_item_id)
        child = by_placement.get(relation.child_item_id)
        if host is None or child is None or host.container_id != child.container_id:
            raise ValueError("Nesting dependency requires host and child placements in the same container")
        dependencies.add(UnloadingDependency(
            relation.child_item_id, relation.host_item_id, relation.container_id, "nested_child_before_host_removal"
        ))
    return tuple(sorted(dependencies, key=lambda value: (
        value.container_id, value.predecessor_item_id, value.successor_item_id, value.reason
    )))


def validate_sequential_unloading(
    items: Iterable[Item],
    containers: Iterable[Container],
    placements: Iterable[Placement],
    unloading_config: dict[str, Any],
    removal_order: Iterable[str],
    *,
    nesting_relations: Iterable[NestingRelation] = (),
    orientation_profile: str = "fixed",
    state_validator: StateValidator | None = None,
) -> SequentialUnloadingValidation:
    """Validate an offline removal sequence with post-removal state checks.

    Built-in validation rechecks geometry/payload and strict static LIFO after
    every accepted removal. A later composition injects a complete Level 1--7
    validator through ``state_validator`` without coupling this pure core to a
    solver or a run directory.
    """
    item_list = list(items)
    container_list = list(containers)
    placement_list = list(placements)
    settings = UnloadingSettings.from_config(unloading_config)
    item_by_id = {item.item_id: item for item in item_list}
    placement_by_id = {placement.item_id: placement for placement in placement_list}
    issues: list[ValidationIssue] = []
    if len(item_by_id) != len(item_list):
        issues.append(ValidationIssue("SEQUENTIAL_DUPLICATE_ITEM", "Sequential input contains duplicate item IDs"))
    if set(item_by_id) != set(placement_by_id):
        issues.append(ValidationIssue("SEQUENTIAL_ITEM_PLACEMENT_MISMATCH", "Sequential input items and placements must match"))
    if issues:
        return SequentialUnloadingValidation(ValidationResult(False, issues), (), ())

    dependencies = build_unloading_dependency_graph(item_list, placement_list, settings, nesting_relations=nesting_relations)
    predecessors: dict[str, list[UnloadingDependency]] = defaultdict(list)
    for dependency in dependencies:
        predecessors[dependency.successor_item_id].append(dependency)

    remaining_ids = set(item_by_id)
    removed_ids: set[str] = set()
    steps: list[SequentialUnloadingStep] = []
    for sequence, item_id in enumerate(removal_order):
        step_issues: list[ValidationIssue] = []
        if item_id not in item_by_id:
            step_issues.append(ValidationIssue("SEQUENTIAL_UNKNOWN_ITEM", f"Removal sequence references unknown item {item_id}", (item_id,)))
        elif item_id not in remaining_ids:
            step_issues.append(ValidationIssue("SEQUENTIAL_DUPLICATE_REMOVAL", f"Item {item_id} is removed more than once", (item_id,)))
        else:
            for edge in (edge for edge in predecessors[item_id] if edge.predecessor_item_id not in removed_ids):
                step_issues.append(ValidationIssue(
                    "SEQUENTIAL_DEPENDENCY_UNMET",
                    f"Item {item_id} cannot be removed before {edge.predecessor_item_id} ({edge.reason})",
                    (edge.predecessor_item_id, item_id), edge.container_id,
                ))
            current_items = [item_by_id[value] for value in sorted(remaining_ids)]
            current_placements = [placement_by_id[value] for value in sorted(remaining_ids)]
            current_lifo = validate_unloading_lifo(current_items, current_placements, unloading_config)
            target_record = next((value for value in current_lifo.records if value.item_id == item_id), None)
            if target_record is not None and target_record.later_priority_blocker_ids:
                step_issues.append(ValidationIssue(
                    "SEQUENTIAL_LIFO_BLOCKED_REMOVAL",
                    f"Item {item_id} still has later delivery blocker(s): " + ", ".join(target_record.later_priority_blocker_ids),
                    (item_id, *target_record.later_priority_blocker_ids), target_record.container_id,
                ))
        accepted = not step_issues
        if accepted:
            remaining_ids.remove(item_id)
            removed_ids.add(item_id)
            remaining_items = [item_by_id[value] for value in sorted(remaining_ids)]
            remaining_placements = [placement_by_id[value] for value in sorted(remaining_ids)]
            geometry = validate_geometry_solution(remaining_items, container_list, remaining_placements, orientation_profile=orientation_profile)
            step_issues.extend(geometry.issues)
            if remaining_items:
                step_issues.extend(validate_unloading_lifo(remaining_items, remaining_placements, unloading_config).result.issues)
            if state_validator is not None:
                step_issues.extend(state_validator(remaining_items, remaining_placements).issues)
            accepted = not step_issues
        steps.append(SequentialUnloadingStep(
            sequence, item_id, accepted, len(remaining_ids),
            tuple(sorted(edge.predecessor_item_id for edge in predecessors.get(item_id, ())),), tuple(step_issues),
        ))
        issues.extend(step_issues)

    missing = sorted(remaining_ids)
    if missing:
        issues.append(ValidationIssue(
            "SEQUENTIAL_ITEMS_NOT_REMOVED", "Removal sequence did not remove all items: " + ", ".join(missing), tuple(missing),
        ))
    return SequentialUnloadingValidation(ValidationResult(not issues, issues), dependencies, tuple(steps))
