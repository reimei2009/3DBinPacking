"""Deterministic explicit-nesting relation construction for Level 6 fixtures."""

from __future__ import annotations

from dataclasses import dataclass

from ..schemas import Item, Placement
from .nesting import NestingAttributes, NestingSettings, attributes_for_item
from .nesting_engine import NestingEvaluationError, NestingRelation, evaluate_nesting


@dataclass(frozen=True)
class NestingConstructionResult:
    policy_id: str
    relations: tuple[NestingRelation, ...]
    eligible_child_count: int
    candidate_relation_count: int
    accepted_relation_count: int
    rejected_candidate_count: int

    def metadata(self) -> dict[str, object]:
        return {
            "nesting_construction_policy": self.policy_id,
            "nesting_eligible_child_count": self.eligible_child_count,
            "nesting_candidate_relation_count": self.candidate_relation_count,
            "nesting_accepted_relation_count": self.accepted_relation_count,
            "nesting_rejected_candidate_count": self.rejected_candidate_count,
        }


def construct_nesting_relations(
    items: list[Item] | tuple[Item, ...],
    placements: list[Placement] | tuple[Placement, ...],
    settings: NestingSettings,
    *,
    existing_relations: list[NestingRelation] | tuple[NestingRelation, ...] = (),
) -> NestingConstructionResult:
    """Build reproducible best-fit nesting chains from declared metadata only.

    This is a fixture construction policy, not a packing solver. It evaluates
    every tentative relation through the canonical nesting engine, so a greedy
    choice cannot bypass compatibility, chain-depth, or cycle validation.
    """
    item_by_id = {item.item_id: item for item in items}
    placement_by_id = _placements_by_id(placements)
    if set(item_by_id) != set(placement_by_id):
        missing = sorted(set(item_by_id) - set(placement_by_id))
        unknown = sorted(set(placement_by_id) - set(item_by_id))
        raise ValueError(
            f"Nesting construction requires matching item/placement IDs; missing={missing}, unknown={unknown}"
        )
    attributes = {item_id: attributes_for_item(item) for item_id, item in item_by_id.items()}
    selected = list(existing_relations)
    try:
        evaluate_nesting(placements, attributes, selected, clearance_mm=settings.clearance_mm)
    except NestingEvaluationError as exc:
        raise ValueError(f"Existing nesting relations are invalid: {exc}") from exc
    existing_children = {relation.child_item_id for relation in selected}
    existing_hosts = {relation.host_item_id for relation in selected}
    eligible_children = [
        item_id for item_id, attributes_value in attributes.items()
        if attributes_value.declared_active
        and attributes_value.nesting_role in {"child", "both"}
        and item_id not in existing_children
    ]
    candidates_seen = 0
    rejected = 0
    for child_id in sorted(
        eligible_children,
        key=lambda item_id: (-_volume(placement_by_id[item_id]), item_id),
    ):
        child = placement_by_id[child_id]
        host_ids = [
            item_id for item_id, attributes_value in attributes.items()
            if item_id != child_id
            and attributes_value.declared_active
            and attributes_value.nesting_role in {"host", "both"}
            and item_id not in existing_hosts
            and placement_by_id[item_id].container_id == child.container_id
        ]
        ranked_hosts = sorted(
            host_ids,
            key=lambda item_id: _host_rank(attributes[item_id], child, item_id),
        )
        for host_id in ranked_hosts:
            candidates_seen += 1
            relation = NestingRelation(host_id, child_id, child.container_id)
            try:
                evaluate_nesting(
                    placements, attributes, [*selected, relation],
                    clearance_mm=settings.clearance_mm,
                )
            except NestingEvaluationError:
                rejected += 1
                continue
            selected.append(relation)
            existing_children.add(child_id)
            existing_hosts.add(host_id)
            break
    relations = tuple(sorted(selected, key=lambda value: (value.host_item_id, value.child_item_id)))
    return NestingConstructionResult(
        settings.construction_policy_id,
        relations,
        len(eligible_children),
        candidates_seen,
        len(relations) - len(existing_relations),
        rejected,
    )


def _placements_by_id(placements: list[Placement] | tuple[Placement, ...]) -> dict[str, Placement]:
    values: dict[str, Placement] = {}
    for placement in placements:
        if placement.item_id in values:
            raise ValueError(f"Duplicate nesting construction placement item ID: {placement.item_id}")
        values[placement.item_id] = placement
    return values


def _volume(placement: Placement) -> float:
    return placement.length_mm * placement.width_mm * placement.height_mm


def _host_rank(attributes: NestingAttributes, child: Placement, item_id: str) -> tuple[float, str]:
    if (
        attributes.inner_length_mm is None
        or attributes.inner_width_mm is None
        or attributes.inner_height_mm is None
    ):
        return (float("inf"), item_id)
    remaining = (
        attributes.inner_length_mm * attributes.inner_width_mm * attributes.inner_height_mm
        - _volume(child)
    )
    return (remaining, item_id)
