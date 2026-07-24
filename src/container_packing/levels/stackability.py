"""Typed Level 4 stackability contract shared by future algorithms/validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..geometry.support import contact_rectangle, evaluate_support
from ..schemas import Item, Placement


@dataclass(frozen=True)
class StackabilitySettings:
    """Versioned project interpretation of the Level 4 data fields."""

    non_stackable_codes: frozenset[str]
    non_stackable_item_ids: frozenset[str]
    non_stackable_policy: str
    maximum_layers_semantics: str
    cap_aggregation: str

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "StackabilitySettings":
        compatibility = config.get("compatibility", {})
        stack_limit = config.get("stack_limit", {})
        if compatibility.get("mode") != "same_stackability_code":
            raise ValueError("Level 4 requires compatibility.mode='same_stackability_code'")
        policy = str(compatibility.get("non_stackable_policy", ""))
        if policy != "floor_only_no_children":
            raise ValueError("Level 4 only supports non_stackable_policy='floor_only_no_children'")
        semantics = str(stack_limit.get("semantics", ""))
        if semantics != "maximum_layers_in_parent_chain_including_root":
            raise ValueError("Unsupported Level 4 max-stack semantics")
        aggregation = str(stack_limit.get("cap_aggregation", ""))
        if aggregation != "minimum_along_parent_chain":
            raise ValueError("Level 4 requires cap_aggregation='minimum_along_parent_chain'")
        return cls(
            frozenset(str(value).strip() for value in compatibility.get("non_stackable_codes", [])),
            frozenset(str(value).strip() for value in compatibility.get("non_stackable_item_ids", [])),
            policy,
            semantics,
            aggregation,
        )


@dataclass(frozen=True)
class StackabilityAttributes:
    item_id: str
    stack_group_id: str
    max_stack_layers: int
    is_non_stackable: bool


def attributes_for_item(item: Item, settings: StackabilitySettings) -> StackabilityAttributes:
    """Read raw fields without mutating the source item or its provenance."""
    try:
        group = str(item.source["stackability_code"]).strip()
    except KeyError as exc:
        raise ValueError(f"Item {item.item_id} has no stackability_code in source data") from exc
    if not group:
        raise ValueError(f"Item {item.item_id} has an empty stackability_code")
    try:
        maximum = int(str(item.source["max_stackability"]).strip())
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Item {item.item_id} has invalid max_stackability") from exc
    if maximum <= 0:
        raise ValueError(f"Item {item.item_id} max_stackability must be positive")
    return StackabilityAttributes(
        item.item_id,
        group,
        maximum,
        item.item_id in settings.non_stackable_item_ids or group in settings.non_stackable_codes,
    )


@dataclass(frozen=True)
class StackParentRelation:
    """Declared value of p[j,i,k] for a non-floor child placement."""

    parent_item_id: str
    child_item_id: str
    container_id: str


@dataclass(frozen=True)
class StackRecord:
    item_id: str
    container_id: str
    direct_parent_item_id: str | None
    stack_id: str | None
    stack_depth: int | None
    stack_layer_count: int | None
    max_stack_layers_effective: int | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "container_id": self.container_id,
            "direct_parent_item_id": self.direct_parent_item_id or "",
            "stack_id": self.stack_id or "",
            "stack_depth": self.stack_depth,
            "stack_layer_count": self.stack_layer_count,
            "max_stack_layers_effective": self.max_stack_layers_effective,
        }


def solution_payload(records: list[StackRecord] | tuple[StackRecord, ...]) -> dict[str, Any]:
    """Return canonical, JSON-safe stack metadata for a future Level 4 run."""
    values = [record.to_dict() for record in records]
    return {
        "stack_records": values,
        "stack_count": len({record.stack_id for record in records if record.stack_id}),
        "maximum_stack_depth": max((record.stack_depth or 0 for record in records), default=0),
    }


def scene_item_metadata(records: list[StackRecord] | tuple[StackRecord, ...]) -> dict[str, dict[str, Any]]:
    """Map canonical stack fields to the backend-neutral scene item metadata."""
    return {
        record.item_id: {
            "direct_parent_item_id": record.direct_parent_item_id,
            "stack_id": record.stack_id,
            "stack_depth": record.stack_depth,
            "stack_layer_count": record.stack_layer_count,
            "max_stack_layers_effective": record.max_stack_layers_effective,
        }
        for record in records
    }


def report_lines(records: list[StackRecord] | tuple[StackRecord, ...]) -> list[str]:
    """Compact markdown lines suitable for the generic run summary."""
    payload = solution_payload(records)
    return [
        f"- Stack count: {payload['stack_count']}",
        f"- Maximum stack depth: {payload['maximum_stack_depth']}",
    ]


def infer_parent_relations(
    placements: list[Placement],
    attributes: dict[str, StackabilityAttributes],
    *,
    epsilon_mm: float,
) -> list[StackParentRelation]:
    """Choose one deterministic compatible geometric parent for each child.

    The primary key is largest contact area, followed by parent item ID. This
    creates a reproducible declared `p[j,i,k]` relation without claiming that
    it represents load transfer.
    """
    relations: list[StackParentRelation] = []
    by_container: dict[str, list[Placement]] = {}
    for placement in placements:
        by_container.setdefault(placement.container_id, []).append(placement)
    for child in sorted(placements, key=lambda value: (value.z_mm, value.item_id)):
        if abs(child.z_mm) <= epsilon_mm:
            continue
        child_attributes = attributes[child.item_id]
        if child_attributes.is_non_stackable:
            continue
        support = evaluate_support(
            child, by_container.get(child.container_id, []), epsilon_mm=epsilon_mm,
        )
        candidates: list[tuple[float, str, Placement]] = []
        for parent_id in support.supporting_item_ids:
            parent = next(value for value in by_container[child.container_id] if value.item_id == parent_id)
            parent_attributes = attributes[parent.item_id]
            if parent_attributes.is_non_stackable or parent_attributes.stack_group_id != child_attributes.stack_group_id:
                continue
            rectangle = contact_rectangle(child, parent)
            if rectangle is None:
                continue
            area = (rectangle[2] - rectangle[0]) * (rectangle[3] - rectangle[1])
            candidates.append((area, parent.item_id, parent))
        if candidates:
            _, _, parent = min(candidates, key=lambda value: (-value[0], value[1]))
            relations.append(StackParentRelation(parent.item_id, child.item_id, child.container_id))
    return relations


def parent_chain(
    item_id: str,
    relations: list[StackParentRelation] | tuple[StackParentRelation, ...],
) -> list[str] | None:
    """Return root-to-item chain, or None when declarations contain a cycle."""
    parents = {relation.child_item_id: relation.parent_item_id for relation in relations}
    chain = [item_id]
    seen = {item_id}
    current = item_id
    while current in parents:
        current = parents[current]
        if current in seen:
            return None
        seen.add(current)
        chain.append(current)
    return list(reversed(chain))


def chain_respects_max_layers(
    item_id: str,
    relations: list[StackParentRelation] | tuple[StackParentRelation, ...],
    attributes: dict[str, StackabilityAttributes],
) -> bool:
    chain = parent_chain(item_id, relations)
    return chain is not None and len(chain) <= min(attributes[value].max_stack_layers for value in chain)
