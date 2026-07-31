"""Level 1--7 state-validation callback for Level 8 sequential replay.

The sequential graph stays pure and solver-free. This adapter supplies the
complete inherited bundle for a *remaining* set of logical items, rebuilding
compound, support, stackability, load-transfer, and balance evidence after
each removal.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Iterable

from ..schemas import Container, Item, Placement, ValidationIssue, ValidationResult
from .level_07_fixture_bundle import validate_level_07_fixture_bundle
from .nesting_engine import NestingRelation
from .level_08_sequential_validation import StateValidator


def filter_remaining_nesting_relations(
    relations: Iterable[NestingRelation], remaining_item_ids: Iterable[str]
) -> tuple[NestingRelation, ...]:
    """Keep only explicit host/child relations whose two members remain.

    Stack parents and load-transfer edges are intentionally not copied from a
    prior state: the Level 6/7 bundle re-infers them from the remaining compound
    placements. This prevents stale support/load evidence after a removal.
    """
    remaining = set(remaining_item_ids)
    return tuple(
        relation for relation in relations
        if relation.host_item_id in remaining and relation.child_item_id in remaining
    )


def build_level_07_remaining_state_validator(
    containers: Iterable[Container],
    config: dict[str, Any],
    *,
    nesting_relations: Iterable[NestingRelation] = (),
) -> StateValidator:
    """Create a pure callback that recalculates the full inherited bundle.

    The input config is deep-copied per callback invocation because rule
    resolvers populate it lazily. No result, relation, or validation document is
    reused from a preceding sequential state.
    """
    container_list = list(containers)
    fixed_relations = tuple(nesting_relations)
    base_config = deepcopy(config)

    def validate(remaining_items: list[Item], remaining_placements: list[Placement]) -> ValidationResult:
        active_relations = filter_remaining_nesting_relations(
            fixed_relations, (item.item_id for item in remaining_items)
        )
        try:
            bundle = validate_level_07_fixture_bundle(
                list(remaining_items), container_list, list(remaining_placements),
                deepcopy(base_config), list(active_relations),
            )
        except (KeyError, TypeError, ValueError) as exc:
            return ValidationResult(False, [ValidationIssue(
                "SEQUENTIAL_INHERITED_STATE_VALIDATION_ERROR",
                f"Level 1--7 remaining-state validation failed to execute: {exc}",
            )])
        return bundle.result

    return validate


@dataclass
class IncrementalLevel07StateValidator:
    """Revalidate only the container changed by one deterministic removal.

    All active Level 1--7 constraints are container-local at this checkpoint.
    A removal cannot create overlap, boundary, payload, or load-bearing excess;
    support/nesting precedence is enforced by the sequential dependency graph.
    The changed container is still rebuilt from its raw remaining snapshot, so
    COG, support, stackability, load transfer, and nesting evidence are never
    reused after a removal.
    """

    containers: dict[str, Container]
    original_container_by_item: dict[str, str]
    base_config: dict[str, Any]
    fixed_relations: tuple[NestingRelation, ...]
    remaining_ids: set[str]
    initial_result: ValidationResult
    container_validations: int = 0
    unchanged_container_cache_hits: int = 0

    def __call__(
        self, remaining_items: list[Item], remaining_placements: list[Placement]
    ) -> ValidationResult:
        observed_ids = {item.item_id for item in remaining_items}
        removed_ids = self.remaining_ids - observed_ids
        if len(removed_ids) != 1:
            return ValidationResult(False, [ValidationIssue(
                "SEQUENTIAL_INCREMENTAL_STATE_TRANSITION_INVALID",
                "Incremental replay requires exactly one removed item per state transition",
            )])
        removed_item_id = next(iter(removed_ids))
        container_id = self.original_container_by_item[removed_item_id]
        self.remaining_ids = observed_ids
        self.unchanged_container_cache_hits += max(0, len(self.containers) - 1)
        return self._validate_container(container_id, remaining_items, remaining_placements)

    def diagnostics(self) -> dict[str, int | str]:
        return {
            "sequential_state_validation_mode": "incremental_container_local_v1",
            "sequential_container_validations": self.container_validations,
            "sequential_unchanged_container_cache_hits": self.unchanged_container_cache_hits,
        }

    def _validate_container(
        self,
        container_id: str,
        remaining_items: list[Item],
        remaining_placements: list[Placement],
    ) -> ValidationResult:
        item_ids = {
            item.item_id for item in remaining_items
            if self.original_container_by_item[item.item_id] == container_id
        }
        if not item_ids:
            return ValidationResult(True, [])
        items = [item for item in remaining_items if item.item_id in item_ids]
        placements = [placement for placement in remaining_placements if placement.item_id in item_ids]
        relations = filter_remaining_nesting_relations(self.fixed_relations, item_ids)
        self.container_validations += 1
        try:
            bundle = validate_level_07_fixture_bundle(
                items,
                [self.containers[container_id]],
                placements,
                deepcopy(self.base_config),
                list(relations),
            )
        except (KeyError, TypeError, ValueError) as exc:
            return ValidationResult(False, [ValidationIssue(
                "SEQUENTIAL_INCREMENTAL_STATE_VALIDATION_ERROR",
                f"Level 1--7 changed-container validation failed to execute: {exc}",
                container_id=container_id,
            )])
        return bundle.result


def build_incremental_level_07_remaining_state_validator(
    items: Iterable[Item],
    containers: Iterable[Container],
    placements: Iterable[Placement],
    config: dict[str, Any],
    *,
    nesting_relations: Iterable[NestingRelation] = (),
) -> IncrementalLevel07StateValidator:
    """Build the scale-oriented equivalent of the legacy full-state callback."""
    item_list = list(items)
    container_list = list(containers)
    placement_list = list(placements)
    placement_by_item = {placement.item_id: placement for placement in placement_list}
    if {item.item_id for item in item_list} != set(placement_by_item):
        raise ValueError("Incremental replay requires one initial placement per item")
    container_by_id = {container.container_id: container for container in container_list}
    original_container_by_item = {
        item_id: placement.container_id for item_id, placement in placement_by_item.items()
    }
    if not set(original_container_by_item.values()) <= set(container_by_id):
        raise ValueError("Incremental replay references an unknown container")
    # Validate the initial snapshot per container. These certificates are only
    # reused while a container is unchanged; they are not copied after removal.
    initial_issues: list[ValidationIssue] = []
    fixed_relations = tuple(nesting_relations)
    validator = IncrementalLevel07StateValidator(
        container_by_id,
        original_container_by_item,
        deepcopy(config),
        fixed_relations,
        {item.item_id for item in item_list},
        ValidationResult(True, []),
    )
    for container_id in sorted(set(original_container_by_item.values())):
        initial_issues.extend(
            validator._validate_container(container_id, item_list, placement_list).issues
        )
    validator.initial_result = ValidationResult(not initial_issues, initial_issues)
    return validator
