"""Typed, explicit nesting capability contract for a future Level 6 runtime."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

from ..schemas import Item


_ROLES = frozenset({"none", "host", "child", "both"})


@dataclass(frozen=True)
class NestingSettings:
    """Versioned Level 6 relation semantics, independent of a solver runtime."""

    contract_version: int
    clearance_mm: float
    missing_metadata_behavior: str
    runtime_semantics_status: str
    construction_policy_id: str

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "NestingSettings":
        if config.get("contract_version") != 1:
            raise ValueError("Level 6 nesting contract_version must be 1")
        if config.get("level_id") != "level_06":
            raise ValueError("Level 6 nesting contract requires level_id='level_06'")
        if config.get("activation") != "explicit_compatibility":
            raise ValueError("Level 6 requires activation='explicit_compatibility'")
        missing = config.get("missing_metadata_behavior")
        if missing != "nesting_disabled_undeclared":
            raise ValueError("Level 6 requires missing_metadata_behavior='nesting_disabled_undeclared'")
        if set(config.get("roles", [])) != _ROLES:
            raise ValueError(f"Level 6 nesting roles must be {sorted(_ROLES)}")
        if config.get("increment_semantics") != "child_declared_increment_height_mm":
            raise ValueError("Level 6 only supports child_declared_increment_height_mm")
        try:
            clearance = float(config.get("dimension_clearance_mm", 0.0))
        except (TypeError, ValueError) as exc:
            raise ValueError("Level 6 dimension_clearance_mm must be a number") from exc
        if not isfinite(clearance) or clearance < 0:
            raise ValueError("Level 6 dimension_clearance_mm must be finite and non-negative")
        runtime = config.get("runtime_semantics")
        if not isinstance(runtime, dict):
            raise ValueError("Level 6 nesting contract requires runtime_semantics")
        expected_runtime = {
            "status": "designed_not_active",
            "relation_source": "explicit_solution_relation",
            "child_coordinate_mode": "logical_member_no_global_box",
            "external_occupancy": "compound_root_effective_envelope",
            "effective_height": "root_outer_height_plus_member_increments",
            "boundary_and_non_overlap": "compound_projection_only",
            "support_and_stackability": "compound_root_external_faces_only",
            "load_transfer": "compound_weight_through_root_external_contacts",
            "internal_load_transfer": "inactive_not_claimed",
        }
        for field, expected in expected_runtime.items():
            if runtime.get(field) != expected:
                raise ValueError(f"Level 6 runtime_semantics.{field} must be {expected!r}")
        construction = config.get("construction_policy")
        expected_construction = {
            "policy_id": "explicit_nesting_best_fit_chain_v1",
            "child_order": "descending_outer_volume_then_item_id",
            "host_ranking": "minimum_remaining_inner_volume_then_item_id",
            "max_direct_children_per_host": 1,
            "relation_source": "explicit_metadata_fixture_only",
        }
        if not isinstance(construction, dict):
            raise ValueError("Level 6 nesting contract requires construction_policy")
        for field, expected in expected_construction.items():
            if construction.get(field) != expected:
                raise ValueError(f"Level 6 construction_policy.{field} must be {expected!r}")
        return cls(
            int(config["contract_version"]), clearance, str(missing),
            runtime["status"], construction["policy_id"],
        )


@dataclass(frozen=True)
class NestingAttributes:
    item_id: str
    nesting_group_id: str | None
    nesting_role: str
    inner_length_mm: float | None
    inner_width_mm: float | None
    inner_height_mm: float | None
    max_nesting_depth: int | None
    nesting_increment_height_mm: float | None
    nesting_data_source: str
    declared_active: bool


@dataclass(frozen=True)
class NestingDecision:
    allowed: bool
    reason: str
    effective_increment_height_mm: float | None = None


class NestingCapabilityProvider:
    """Evaluate declared nesting compatibility without changing geometry."""

    def __init__(self, attributes: dict[str, NestingAttributes], *, clearance_mm: float = 0.0):
        if clearance_mm < 0:
            raise ValueError("Nesting clearance_mm must be non-negative")
        self.attributes = dict(attributes)
        self.clearance_mm = float(clearance_mm)

    def can_nest(
        self,
        parent_item_id: str,
        child_item_id: str,
        *,
        child_length_mm: float,
        child_width_mm: float,
        child_height_mm: float,
        resulting_depth: int,
    ) -> NestingDecision:
        parent = self.attributes.get(parent_item_id)
        child = self.attributes.get(child_item_id)
        if parent is None or child is None:
            return NestingDecision(False, "unknown_item")
        if not parent.declared_active or not child.declared_active:
            return NestingDecision(False, "nesting_disabled_undeclared")
        if parent.nesting_role not in {"host", "both"}:
            return NestingDecision(False, "parent_role_not_host")
        if child.nesting_role not in {"child", "both"}:
            return NestingDecision(False, "child_role_not_child")
        if parent.nesting_group_id != child.nesting_group_id:
            return NestingDecision(False, "nesting_group_mismatch")
        if parent.inner_length_mm is None or parent.inner_width_mm is None or parent.inner_height_mm is None:
            return NestingDecision(False, "parent_inner_dimensions_undeclared")
        if parent.max_nesting_depth is None or resulting_depth > parent.max_nesting_depth:
            return NestingDecision(False, "maximum_nesting_depth_exceeded")
        if child.nesting_increment_height_mm is None:
            return NestingDecision(False, "child_increment_height_undeclared")
        clearance = self.clearance_mm
        if (
            child_length_mm + clearance > parent.inner_length_mm
            or child_width_mm + clearance > parent.inner_width_mm
            or child_height_mm + clearance > parent.inner_height_mm
        ):
            return NestingDecision(False, "inner_dimensions_insufficient")
        return NestingDecision(True, "declared_compatible", child.nesting_increment_height_mm)


def attributes_for_item(item: Item) -> NestingAttributes:
    """Read optional data without treating legacy nesting_height as active metadata."""
    source = item.source
    data_source = _text(source.get("nesting_data_source")) or "undeclared"
    role = (_text(source.get("nesting_role")) or "none").lower()
    if role not in _ROLES:
        raise ValueError(f"Item {item.item_id} has unsupported nesting_role {role!r}")
    values = NestingAttributes(
        item_id=item.item_id,
        nesting_group_id=_text(source.get("nesting_group_id")),
        nesting_role=role,
        inner_length_mm=_optional_positive(source.get("inner_length_mm"), "inner_length_mm", item.item_id),
        inner_width_mm=_optional_positive(source.get("inner_width_mm"), "inner_width_mm", item.item_id),
        inner_height_mm=_optional_positive(source.get("inner_height_mm"), "inner_height_mm", item.item_id),
        max_nesting_depth=_optional_positive_int(source.get("max_nesting_depth"), item.item_id),
        nesting_increment_height_mm=_optional_positive(source.get("nesting_increment_height_mm"), "nesting_increment_height_mm", item.item_id),
        nesting_data_source=data_source,
        declared_active=data_source != "undeclared" and role != "none",
    )
    if not values.declared_active:
        return values
    if not values.nesting_group_id:
        raise ValueError(f"Item {item.item_id} declares nesting but has no nesting_group_id")
    if values.nesting_role in {"host", "both"} and (
        values.inner_length_mm is None or values.inner_width_mm is None
        or values.inner_height_mm is None or values.max_nesting_depth is None
    ):
        raise ValueError(f"Nesting host item {item.item_id} requires inner dimensions and max_nesting_depth")
    if values.nesting_role in {"child", "both"} and values.nesting_increment_height_mm is None:
        raise ValueError(f"Nesting child item {item.item_id} requires nesting_increment_height_mm")
    return values


def _text(value: Any) -> str | None:
    if value is None:
        return None
    result = str(value).strip()
    return result or None


def _optional_positive(value: Any, field: str, item_id: str) -> float | None:
    text = _text(value)
    if text is None:
        return None
    try:
        number = float(text)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Item {item_id} {field} must be numeric") from exc
    if not isfinite(number) or number <= 0:
        raise ValueError(f"Item {item_id} {field} must be positive")
    return number


def _optional_positive_int(value: Any, item_id: str) -> int | None:
    number = _optional_positive(value, "max_nesting_depth", item_id)
    if number is None:
        return None
    if number % 1:
        raise ValueError(f"Item {item_id} max_nesting_depth must be an integer")
    return int(number)
