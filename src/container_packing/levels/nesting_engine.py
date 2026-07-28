"""Pure explicit-nesting graph and effective-height evaluation for Level 6."""

from __future__ import annotations

from dataclasses import dataclass

from ..schemas import Placement
from .nesting import NestingAttributes, NestingCapabilityProvider


class NestingEvaluationError(ValueError):
    """Raised when declared nesting relations cannot form a valid chain."""


@dataclass(frozen=True)
class NestingRelation:
    """A direct host-to-child declaration; depth is always recomputed."""

    host_item_id: str
    child_item_id: str
    container_id: str

    def to_dict(self) -> dict[str, str]:
        return {
            "host_item_id": self.host_item_id,
            "child_item_id": self.child_item_id,
            "container_id": self.container_id,
        }


@dataclass(frozen=True)
class NestingRecord:
    item_id: str
    container_id: str
    root_item_id: str
    host_item_id: str | None
    nesting_depth: int
    declared_outer_height_mm: float
    vertical_contribution_height_mm: float
    chain_effective_height_mm: float
    nesting_increment_height_mm: float | None

    def to_dict(self) -> dict[str, object]:
        return {
            "item_id": self.item_id,
            "container_id": self.container_id,
            "root_item_id": self.root_item_id,
            "host_item_id": self.host_item_id,
            "nesting_depth": self.nesting_depth,
            "declared_outer_height_mm": self.declared_outer_height_mm,
            "vertical_contribution_height_mm": self.vertical_contribution_height_mm,
            "chain_effective_height_mm": self.chain_effective_height_mm,
            "nesting_increment_height_mm": self.nesting_increment_height_mm,
        }


@dataclass(frozen=True)
class NestingEvaluation:
    records: tuple[NestingRecord, ...]
    relations: tuple[NestingRelation, ...]


def evaluate_nesting(
    placements: list[Placement] | tuple[Placement, ...],
    attributes: dict[str, NestingAttributes],
    relations: list[NestingRelation] | tuple[NestingRelation, ...],
    *,
    clearance_mm: float = 0.0,
) -> NestingEvaluation:
    """Validate explicit relations and calculate effective vertical chain height.

    The root contributes its outer height.  Each nested child contributes its
    declared ``nesting_increment_height_mm``.  The function intentionally does
    not reinterpret placement geometry or relax overlap checks; a future Level
    6 runtime will compose this result with the inherited Level 5 validator.
    """
    placements_by_id: dict[str, Placement] = {}
    for placement in placements:
        if placement.item_id in placements_by_id:
            raise NestingEvaluationError(f"Duplicate nesting placement item ID: {placement.item_id}")
        if placement.item_id not in attributes:
            raise NestingEvaluationError(f"Missing nesting attributes for item {placement.item_id}")
        placements_by_id[placement.item_id] = placement

    parents: dict[str, NestingRelation] = {}
    children: dict[str, NestingRelation] = {}
    for relation in relations:
        host = placements_by_id.get(relation.host_item_id)
        child = placements_by_id.get(relation.child_item_id)
        if host is None or child is None:
            raise NestingEvaluationError(
                f"Nesting relation {relation.host_item_id}->{relation.child_item_id} references an unknown placement"
            )
        if relation.host_item_id == relation.child_item_id:
            raise NestingEvaluationError(f"Item {relation.child_item_id} cannot nest inside itself")
        if relation.container_id != host.container_id or relation.container_id != child.container_id:
            raise NestingEvaluationError(
                f"Nesting relation {relation.host_item_id}->{relation.child_item_id} must use its placements' container"
            )
        if relation.child_item_id in parents:
            raise NestingEvaluationError(f"Item {relation.child_item_id} has multiple nesting hosts")
        if relation.host_item_id in children:
            raise NestingEvaluationError(f"Host {relation.host_item_id} has multiple nested children")
        parents[relation.child_item_id] = relation
        children[relation.host_item_id] = relation

    _assert_acyclic(parents)
    depth_cache: dict[str, int] = {}

    def depth(item_id: str) -> int:
        if item_id not in parents:
            return 0
        cached = depth_cache.get(item_id)
        if cached is not None:
            return cached
        value = depth(parents[item_id].host_item_id) + 1
        depth_cache[item_id] = value
        return value

    provider = NestingCapabilityProvider(attributes, clearance_mm=clearance_mm)
    for relation in relations:
        child = placements_by_id[relation.child_item_id]
        resulting_depth = depth(relation.child_item_id)
        decision = provider.can_nest(
            relation.host_item_id,
            relation.child_item_id,
            child_length_mm=child.length_mm,
            child_width_mm=child.width_mm,
            child_height_mm=child.height_mm,
            resulting_depth=resulting_depth,
        )
        if not decision.allowed:
            raise NestingEvaluationError(
                f"Nesting relation {relation.host_item_id}->{relation.child_item_id} is invalid: {decision.reason}"
            )
        ancestor_id = relation.host_item_id
        while True:
            cap = attributes[ancestor_id].max_nesting_depth
            if cap is not None and resulting_depth > cap:
                raise NestingEvaluationError(
                    f"Nesting relation {relation.host_item_id}->{relation.child_item_id} is invalid: "
                    f"maximum_nesting_depth_exceeded for host {ancestor_id}"
                )
            ancestor_relation = parents.get(ancestor_id)
            if ancestor_relation is None:
                break
            ancestor_id = ancestor_relation.host_item_id

    records_by_id: dict[str, NestingRecord] = {}

    def record(item_id: str) -> NestingRecord:
        cached = records_by_id.get(item_id)
        if cached is not None:
            return cached
        placement = placements_by_id[item_id]
        relation = parents.get(item_id)
        if relation is None:
            result = NestingRecord(
                item_id=item_id,
                container_id=placement.container_id,
                root_item_id=item_id,
                host_item_id=None,
                nesting_depth=0,
                declared_outer_height_mm=placement.height_mm,
                vertical_contribution_height_mm=placement.height_mm,
                chain_effective_height_mm=placement.height_mm,
                nesting_increment_height_mm=None,
            )
        else:
            host_record = record(relation.host_item_id)
            increment = attributes[item_id].nesting_increment_height_mm
            if increment is None:  # Defensive: provider has already rejected this state.
                raise NestingEvaluationError(f"Nested child {item_id} has no increment height")
            result = NestingRecord(
                item_id=item_id,
                container_id=placement.container_id,
                root_item_id=host_record.root_item_id,
                host_item_id=relation.host_item_id,
                nesting_depth=host_record.nesting_depth + 1,
                declared_outer_height_mm=placement.height_mm,
                vertical_contribution_height_mm=increment,
                chain_effective_height_mm=host_record.chain_effective_height_mm + increment,
                nesting_increment_height_mm=increment,
            )
        records_by_id[item_id] = result
        return result

    for item_id in placements_by_id:
        record(item_id)
    return NestingEvaluation(
        tuple(sorted(records_by_id.values(), key=lambda value: value.item_id)),
        tuple(sorted(relations, key=lambda value: (value.host_item_id, value.child_item_id))),
    )


def _assert_acyclic(parents: dict[str, NestingRelation]) -> None:
    for start in parents:
        seen: set[str] = set()
        current = start
        while current in parents:
            if current in seen:
                raise NestingEvaluationError(f"Nesting relation cycle includes {current}")
            seen.add(current)
            current = parents[current].host_item_id
