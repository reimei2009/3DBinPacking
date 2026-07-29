"""Level 1--7 state-validation callback for Level 8 sequential replay.

The sequential graph stays pure and solver-free. This adapter supplies the
complete inherited bundle for a *remaining* set of logical items, rebuilding
compound, support, stackability, load-transfer, and balance evidence after
each removal.
"""

from __future__ import annotations

from copy import deepcopy
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
