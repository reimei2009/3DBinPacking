"""Independent boundary, non-overlap, and support checks over nesting compounds."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..geometry.support import evaluate_support
from ..schemas import Container, Item, Placement, ValidationIssue, ValidationResult
from .level_01_validation import boxes_intersect
from .level_06_validation import validate_nesting
from .nesting import NestingSettings, attributes_for_item
from .nesting_engine import NestingRelation
from .nesting_runtime import (
    NestingCompoundProjection,
    NestingRuntimeProjection,
    compound_to_external_placement,
    project_nesting_compounds,
)


@dataclass(frozen=True)
class CompoundSupportRecord:
    root_item_id: str
    container_id: str
    is_on_floor: bool
    supporting_root_item_ids: tuple[str, ...]
    support_area_mm2: float
    base_area_mm2: float
    exact_support_ratio: float
    center_supported: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "root_item_id": self.root_item_id,
            "container_id": self.container_id,
            "is_on_floor": self.is_on_floor,
            "supporting_root_item_ids": list(self.supporting_root_item_ids),
            "support_area_mm2": self.support_area_mm2,
            "base_area_mm2": self.base_area_mm2,
            "exact_support_ratio": self.exact_support_ratio,
            "center_supported": self.center_supported,
        }


@dataclass(frozen=True)
class Level06CompoundGeometryValidation:
    result: ValidationResult
    projection: NestingRuntimeProjection | None
    support_records: tuple[CompoundSupportRecord, ...]

    def payload(self) -> dict[str, Any]:
        return {
            "valid": self.result.valid,
            "model": "compound_root_effective_envelope_geometry_v1",
            "compounds": [] if self.projection is None else [
                compound.to_dict() for compound in self.projection.compounds
            ],
            "support_records": [record.to_dict() for record in self.support_records],
            "violations": [
                {
                    "code": issue.code,
                    "message": issue.message,
                    "item_ids": list(issue.item_ids),
                    "container_id": issue.container_id,
                }
                for issue in self.result.issues
            ],
        }


def validate_compound_geometry(
    items: list[Item],
    containers: list[Container],
    placements: list[Placement],
    relations: list[NestingRelation],
    nesting_config: dict[str, Any],
    *,
    support_threshold: float,
    support_epsilon_mm: float,
    coordinate_tolerance_mm: float = 1e-4,
) -> Level06CompoundGeometryValidation:
    """Validate external compound envelopes independently from raw child boxes.

    The caller supplies explicit relations.  Raw nested members are deliberately
    excluded from pairwise external overlap and support checks; their root
    compound carries the chain's effective height and total external weight.
    """
    if not 0 < support_threshold <= 1:
        raise ValueError("support_threshold must be in (0, 1]")
    if support_epsilon_mm <= 0 or coordinate_tolerance_mm < 0:
        raise ValueError("support_epsilon_mm must be positive and coordinate tolerance non-negative")
    settings = NestingSettings.from_config(nesting_config)
    nesting = validate_nesting(
        items, placements, relations, clearance_mm=settings.clearance_mm
    )
    if not nesting.result.valid:
        return Level06CompoundGeometryValidation(nesting.result, None, ())
    attributes = {item.item_id: attributes_for_item(item) for item in items}
    projection = project_nesting_compounds(
        placements, attributes, relations, clearance_mm=settings.clearance_mm
    )
    issues: list[ValidationIssue] = []
    container_by_id = {container.container_id: container for container in containers}
    envelope_by_root = {
        compound.root_item_id: compound_to_external_placement(compound)
        for compound in projection.compounds
    }
    by_container: dict[str, list[Placement]] = {}
    for compound in projection.compounds:
        envelope = envelope_by_root[compound.root_item_id]
        container = container_by_id.get(compound.container_id)
        if container is None:
            issues.append(ValidationIssue(
                "UNKNOWN_COMPOUND_CONTAINER",
                f"Compound root {compound.root_item_id} references unknown container {compound.container_id}",
                compound.member_item_ids, compound.container_id,
            ))
            continue
        by_container.setdefault(compound.container_id, []).append(envelope)
        if min(envelope.x_mm, envelope.y_mm, envelope.z_mm) < -coordinate_tolerance_mm:
            issues.append(ValidationIssue(
                "COMPOUND_NEGATIVE_COORDINATE",
                f"Compound root {compound.root_item_id} has a negative external coordinate",
                compound.member_item_ids, compound.container_id,
            ))
        ends = (
            (envelope.x_mm + envelope.length_mm, container.length_mm, "length"),
            (envelope.y_mm + envelope.width_mm, container.width_mm, "width"),
            (envelope.z_mm + envelope.height_mm, container.height_mm, "height"),
        )
        for end, limit, axis in ends:
            if end > limit + coordinate_tolerance_mm:
                issues.append(ValidationIssue(
                    "COMPOUND_OUT_OF_BOUNDS",
                    f"Compound root {compound.root_item_id} exceeds container {axis}",
                    compound.member_item_ids, compound.container_id,
                ))
    for container_id, envelopes in by_container.items():
        for index, first in enumerate(envelopes):
            for second in envelopes[index + 1:]:
                if boxes_intersect(first, second, coordinate_tolerance_mm):
                    issues.append(ValidationIssue(
                        "COMPOUND_OVERLAP",
                        f"Compound roots {first.item_id} and {second.item_id} overlap",
                        tuple(sorted((*_members(projection, first.item_id), *_members(projection, second.item_id)))),
                        container_id,
                    ))
    records: list[CompoundSupportRecord] = []
    for container_id, envelopes in by_container.items():
        for envelope in sorted(envelopes, key=lambda value: value.item_id):
            support = evaluate_support(
                envelope, envelopes, epsilon_mm=support_epsilon_mm
            )
            members = _members(projection, envelope.item_id)
            if not support.is_on_floor and not support.supporting_item_ids:
                issues.append(ValidationIssue(
                    "COMPOUND_UNSUPPORTED",
                    f"Compound root {envelope.item_id} is above floor without an external supporting compound",
                    members, container_id,
                ))
            if support.exact_support_ratio + 1e-12 < support_threshold:
                issues.append(ValidationIssue(
                    "COMPOUND_INSUFFICIENT_SUPPORT_RATIO",
                    f"Compound root {envelope.item_id} exact support ratio "
                    f"{support.exact_support_ratio:.6f} is below {support_threshold:.6f}",
                    members, container_id,
                ))
            if not support.center_supported:
                issues.append(ValidationIssue(
                    "COMPOUND_CENTER_NOT_SUPPORTED",
                    f"Compound root {envelope.item_id} base center is not externally supported",
                    members, container_id,
                ))
            records.append(CompoundSupportRecord(
                envelope.item_id, container_id, support.is_on_floor,
                support.supporting_item_ids, support.support_area_mm2,
                support.base_area_mm2, support.exact_support_ratio,
                support.center_supported,
            ))
    return Level06CompoundGeometryValidation(
        ValidationResult(not issues, issues), projection, tuple(records)
    )


def _members(projection: NestingRuntimeProjection, root_item_id: str) -> tuple[str, ...]:
    return next(
        compound.member_item_ids
        for compound in projection.compounds
        if compound.root_item_id == root_item_id
    )
