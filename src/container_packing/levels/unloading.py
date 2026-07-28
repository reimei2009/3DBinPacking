"""Pure Level 8 delivery-order and straight-path unloading primitives.

This module intentionally has no solver, registry, or output side effects.  It
describes the static accessibility evidence that a future Level 8 validator and
delivery-aware construction policy will consume.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Iterable

from ..schemas import Item, Placement


_DOOR_FACES = frozenset({"x_min", "x_max", "y_min", "y_max"})


@dataclass(frozen=True)
class UnloadingSettings:
    """Declared Level 8 static unload-path semantics."""

    door_face: str
    path_clearance_mm: float
    delivery_priority_direction: str
    rehandle_count_mode: str
    profile_source: str

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "UnloadingSettings":
        if config.get("contract_version") != 1:
            raise ValueError("Level 8 unloading contract_version must be 1")
        if config.get("level_id") != "level_08":
            raise ValueError("Level 8 unloading contract requires level_id='level_08'")
        if config.get("status") != "data_contract_only":
            raise ValueError("Level 8 unloading contract must remain data_contract_only")
        policy = config.get("unloading_policy")
        if not isinstance(policy, dict):
            raise ValueError("Level 8 unloading contract requires unloading_policy")
        door_face = policy.get("door_face")
        if door_face not in _DOOR_FACES:
            raise ValueError(f"Level 8 door_face must be one of {sorted(_DOOR_FACES)}")
        direction = policy.get("delivery_priority_direction")
        if direction != "ascending_is_earlier_delivery":
            raise ValueError("Level 8 delivery_priority_direction must be 'ascending_is_earlier_delivery'")
        mode = policy.get("rehandle_count_mode")
        if mode != "direct_later_priority_blockers_v1":
            raise ValueError("Level 8 rehandle_count_mode must be 'direct_later_priority_blockers_v1'")
        source = policy.get("profile_source")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("Level 8 unloading_policy.profile_source must be a non-empty string")
        try:
            clearance = float(policy.get("path_clearance_mm", 0.0))
        except (TypeError, ValueError) as exc:
            raise ValueError("Level 8 path_clearance_mm must be a finite non-negative number") from exc
        if not isfinite(clearance) or clearance < 0:
            raise ValueError("Level 8 path_clearance_mm must be a finite non-negative number")
        return cls(str(door_face), clearance, str(direction), str(mode), source.strip())


@dataclass(frozen=True)
class DeliveryAttributes:
    item_id: str
    delivery_priority: int | None
    delivery_stop_id: str | None
    delivery_data_source: str
    declared_active: bool


@dataclass(frozen=True)
class UnloadingAccessibility:
    item_id: str
    container_id: str
    delivery_priority: int
    delivery_stop_id: str
    directly_accessible: bool
    lifo_compliant: bool
    blocking_item_ids: tuple[str, ...]
    later_priority_blocker_ids: tuple[str, ...]
    non_later_blocker_ids: tuple[str, ...]
    minimum_rehandle_count: int
    door_face: str
    path_clearance_mm: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "item_id": self.item_id,
            "container_id": self.container_id,
            "delivery_priority": self.delivery_priority,
            "delivery_stop_id": self.delivery_stop_id,
            "directly_accessible": self.directly_accessible,
            "lifo_compliant": self.lifo_compliant,
            "blocking_item_ids": list(self.blocking_item_ids),
            "later_priority_blocker_ids": list(self.later_priority_blocker_ids),
            "non_later_blocker_ids": list(self.non_later_blocker_ids),
            "minimum_rehandle_count": self.minimum_rehandle_count,
            "door_face": self.door_face,
            "path_clearance_mm": self.path_clearance_mm,
        }


def delivery_attributes_for_item(item: Item) -> DeliveryAttributes:
    """Return explicit delivery metadata without guessing from item geometry."""
    source = item.source
    data_source = _text(source.get("delivery_data_source")) or "undeclared"
    priority_text = _text(source.get("delivery_priority"))
    stop_id = _text(source.get("delivery_stop_id"))
    if data_source == "undeclared" and priority_text is None and stop_id is None:
        return DeliveryAttributes(item.item_id, None, None, "undeclared", False)
    if data_source == "undeclared":
        raise ValueError(f"Item {item.item_id} has delivery fields but delivery_data_source is undeclared")
    if priority_text is None or stop_id is None:
        raise ValueError(
            f"Item {item.item_id} requires delivery_priority and delivery_stop_id when delivery metadata is declared"
        )
    try:
        priority = int(priority_text)
    except ValueError as exc:
        raise ValueError(f"Item {item.item_id} delivery_priority must be a positive integer") from exc
    if str(priority) != priority_text or priority <= 0:
        raise ValueError(f"Item {item.item_id} delivery_priority must be a positive integer")
    return DeliveryAttributes(item.item_id, priority, stop_id, data_source, True)


def assess_unloading_accessibility(
    items: Iterable[Item],
    placements: Iterable[Placement],
    settings: UnloadingSettings,
    *,
    tolerance_mm: float = 1e-6,
) -> tuple[UnloadingAccessibility, ...]:
    """Calculate direct straight-line unloading evidence for final placements.

    A blocker is closer to the configured door and intersects the moving item's
    swept cross-section.  Only blockers with a *later* delivery priority count
    as rehandles in this first static model.  Earlier/same-stop blockers can be
    removed before the target and are retained as evidence, not violations.
    """
    if tolerance_mm < 0:
        raise ValueError("tolerance_mm must be non-negative")
    attributes = {item.item_id: delivery_attributes_for_item(item) for item in items}
    if not attributes:
        return ()
    inactive = [value.item_id for value in attributes.values() if not value.declared_active]
    if inactive:
        raise ValueError(
            "Level 8 unloading is disabled because delivery metadata is undeclared for: "
            + ", ".join(sorted(inactive))
        )
    _validate_priority_stop_mapping(attributes.values())
    placement_list = tuple(placements)
    unknown = sorted({placement.item_id for placement in placement_list} - set(attributes))
    if unknown:
        raise ValueError("Unloading placements contain unknown items: " + ", ".join(unknown))
    records: list[UnloadingAccessibility] = []
    for target in sorted(placement_list, key=lambda value: (value.container_id, value.item_id)):
        target_attributes = attributes[target.item_id]
        blockers = sorted(
            (
                other for other in placement_list
                if other.container_id == target.container_id
                and other.item_id != target.item_id
                and _blocks_straight_path(target, other, settings, tolerance_mm)
            ),
            key=lambda value: value.item_id,
        )
        later = tuple(
            value.item_id for value in blockers
            if attributes[value.item_id].delivery_priority > target_attributes.delivery_priority
        )
        non_later = tuple(value.item_id for value in blockers if value.item_id not in set(later))
        records.append(UnloadingAccessibility(
            item_id=target.item_id,
            container_id=target.container_id,
            delivery_priority=target_attributes.delivery_priority,
            delivery_stop_id=target_attributes.delivery_stop_id,
            directly_accessible=not blockers,
            lifo_compliant=not later,
            blocking_item_ids=tuple(value.item_id for value in blockers),
            later_priority_blocker_ids=later,
            non_later_blocker_ids=non_later,
            minimum_rehandle_count=len(later),
            door_face=settings.door_face,
            path_clearance_mm=settings.path_clearance_mm,
        ))
    return tuple(records)


def prospective_direct_rehandle_delta(
    items_by_id: dict[str, Item],
    placements: Iterable[Placement],
    candidate: Placement,
    settings: UnloadingSettings,
    *,
    tolerance_mm: float = 1e-6,
) -> tuple[int, int]:
    """Return the LIFO impact of adding one candidate placement.

    The complete accessibility matrix is intentionally reserved for final
    validation.  During constructive search every existing pair is identical
    across alternatives in the same container state, so recomputing that
    matrix for every extreme point is unnecessary and becomes cubic in the
    number of items.  This helper evaluates only pairs involving ``candidate``
    and returns ``(direct_rehandles, later_blockers)`` contributed by it.
    """
    if candidate.item_id not in items_by_id:
        raise ValueError(f"Candidate {candidate.item_id} is absent from delivery metadata")
    candidate_attributes = delivery_attributes_for_item(items_by_id[candidate.item_id])
    if not candidate_attributes.declared_active or candidate_attributes.delivery_priority is None:
        raise ValueError(f"Candidate {candidate.item_id} has undeclared delivery metadata")

    direct_rehandles = 0
    later_blockers = 0
    for existing in placements:
        if existing.container_id != candidate.container_id:
            continue
        existing_item = items_by_id.get(existing.item_id)
        if existing_item is None:
            raise ValueError(f"Placement {existing.item_id} is absent from delivery metadata")
        existing_attributes = delivery_attributes_for_item(existing_item)
        if not existing_attributes.declared_active or existing_attributes.delivery_priority is None:
            raise ValueError(f"Placement {existing.item_id} has undeclared delivery metadata")

        # Candidate blocks an already placed earlier delivery item.
        if (
            _blocks_straight_path(existing, candidate, settings, tolerance_mm)
            and candidate_attributes.delivery_priority > existing_attributes.delivery_priority
        ):
            direct_rehandles += 1
            later_blockers += 1

        # An existing later delivery item blocks the candidate itself.
        if (
            _blocks_straight_path(candidate, existing, settings, tolerance_mm)
            and existing_attributes.delivery_priority > candidate_attributes.delivery_priority
        ):
            direct_rehandles += 1
            later_blockers += 1
    return direct_rehandles, later_blockers


def is_later_priority_direct_blocker(
    items_by_id: dict[str, Item], target: Placement, blocker: Placement,
    settings: UnloadingSettings, *, tolerance_mm: float = 1e-6,
) -> bool:
    """Whether ``blocker`` creates one strict-LIFO rehandle for ``target``.

    This narrow primitive is shared by final validation and bounded local
    repair.  It has no solver state and deliberately models only the static
    straight-path convention declared by the Level 8 contract.
    """
    if target.item_id == blocker.item_id or target.container_id != blocker.container_id:
        return False
    target_item = items_by_id.get(target.item_id)
    blocker_item = items_by_id.get(blocker.item_id)
    if target_item is None or blocker_item is None:
        raise ValueError("Unloading blocker check received an item absent from delivery metadata")
    target_attributes = delivery_attributes_for_item(target_item)
    blocker_attributes = delivery_attributes_for_item(blocker_item)
    if (
        not target_attributes.declared_active
        or not blocker_attributes.declared_active
        or target_attributes.delivery_priority is None
        or blocker_attributes.delivery_priority is None
    ):
        raise ValueError("Unloading blocker check requires declared delivery metadata")
    return (
        blocker_attributes.delivery_priority > target_attributes.delivery_priority
        and _blocks_straight_path(target, blocker, settings, tolerance_mm)
    )


def _validate_priority_stop_mapping(attributes: Iterable[DeliveryAttributes]) -> None:
    by_priority: dict[int, set[str]] = {}
    for value in attributes:
        assert value.delivery_priority is not None and value.delivery_stop_id is not None
        by_priority.setdefault(value.delivery_priority, set()).add(value.delivery_stop_id)
    ambiguous = sorted(priority for priority, stops in by_priority.items() if len(stops) > 1)
    if ambiguous:
        raise ValueError(
            "Each delivery_priority must map to one delivery_stop_id; ambiguous priorities: "
            + ", ".join(str(value) for value in ambiguous)
        )


def _blocks_straight_path(
    target: Placement,
    other: Placement,
    settings: UnloadingSettings,
    tolerance_mm: float,
) -> bool:
    face = settings.door_face
    if face == "x_min":
        closer = other.x_mm + other.length_mm <= target.x_mm + tolerance_mm
        cross_axes = ((target.y_mm, target.width_mm, other.y_mm, other.width_mm), (target.z_mm, target.height_mm, other.z_mm, other.height_mm))
    elif face == "x_max":
        closer = other.x_mm >= target.x_mm + target.length_mm - tolerance_mm
        cross_axes = ((target.y_mm, target.width_mm, other.y_mm, other.width_mm), (target.z_mm, target.height_mm, other.z_mm, other.height_mm))
    elif face == "y_min":
        closer = other.y_mm + other.width_mm <= target.y_mm + tolerance_mm
        cross_axes = ((target.x_mm, target.length_mm, other.x_mm, other.length_mm), (target.z_mm, target.height_mm, other.z_mm, other.height_mm))
    else:  # y_max
        closer = other.y_mm >= target.y_mm + target.width_mm - tolerance_mm
        cross_axes = ((target.x_mm, target.length_mm, other.x_mm, other.length_mm), (target.z_mm, target.height_mm, other.z_mm, other.height_mm))
    return closer and all(
        _overlaps_with_clearance(*axis, settings.path_clearance_mm, tolerance_mm)
        for axis in cross_axes
    )


def _overlaps_with_clearance(
    target_start: float,
    target_size: float,
    other_start: float,
    other_size: float,
    clearance: float,
    tolerance_mm: float,
) -> bool:
    target_end = target_start + target_size
    other_end = other_start + other_size
    return other_start < target_end + clearance - tolerance_mm and other_end > target_start - clearance + tolerance_mm


def _text(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None
