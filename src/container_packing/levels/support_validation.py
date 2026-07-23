"""Reusable independent validation for base-support packing levels.

This module composes the canonical geometry/payload validator with exact union
support-area checks.  A level selects its orientation profile explicitly;
support geometry itself remains independent of solver state.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from ..geometry.support import dense_supported_points, evaluate_support
from ..schemas import Container, Item, Placement, ValidationIssue, ValidationResult
from .level_01_validation import validate_solution as validate_geometry_solution


@dataclass(frozen=True)
class SupportRecord:
    item_id: str
    container_id: str
    is_on_floor: bool
    supporting_item_ids: tuple[str, ...]
    support_area_mm2: float
    base_area_mm2: float
    exact_support_ratio: float
    dense_grid_supported_points: int
    dense_grid_size: int
    dense_grid_ratio: float
    center_supported: bool

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["supporting_item_ids"] = ",".join(self.supporting_item_ids)
        return value


@dataclass(frozen=True)
class SupportValidation:
    result: ValidationResult
    support_records: tuple[SupportRecord, ...]
    threshold: float
    dense_grid_x: int
    dense_grid_y: int
    orientation_profile: str

    def payload(self) -> dict[str, Any]:
        return {
            "valid": self.result.valid,
            "support_threshold": self.threshold,
            "orientation_profile": self.orientation_profile,
            "dense_grid": {"x": self.dense_grid_x, "y": self.dense_grid_y},
            "records": [record.to_dict() for record in self.support_records],
        }


def validate_supported_solution(
    items: list[Item],
    containers: list[Container],
    placements: list[Placement],
    *,
    orientation_profile: str,
    support_threshold: float = 0.8,
    support_epsilon_mm: float = 1e-4,
    dense_grid_x: int = 16,
    dense_grid_y: int = 16,
    coordinate_tolerance: float = 1e-4,
    weight_tolerance: float = 1e-6,
) -> SupportValidation:
    """Recalculate geometry, orientation, and support from final placements."""
    if not 0 < support_threshold <= 1:
        raise ValueError("support_threshold must be in (0, 1]")
    if support_epsilon_mm <= 0 or dense_grid_x <= 0 or dense_grid_y <= 0:
        raise ValueError("support epsilon and dense-grid dimensions must be positive")

    base = validate_geometry_solution(
        items,
        containers,
        placements,
        coordinate_tolerance=coordinate_tolerance,
        weight_tolerance=weight_tolerance,
        orientation_profile=orientation_profile,
    )
    issues = list(base.issues)
    by_container: dict[str, list[Placement]] = {}
    for placement in placements:
        by_container.setdefault(placement.container_id, []).append(placement)

    records: list[SupportRecord] = []
    for placement in placements:
        support = evaluate_support(
            placement,
            by_container.get(placement.container_id, []),
            epsilon_mm=support_epsilon_mm,
        )
        dense_size = dense_grid_x * dense_grid_y
        dense_count = dense_size if support.is_on_floor else dense_supported_points(
            placement, support.contact_rectangles, dense_grid_x, dense_grid_y, support_epsilon_mm,
        )
        if not support.is_on_floor and not support.supporting_item_ids:
            issues.append(ValidationIssue(
                "UNSUPPORTED_ITEM",
                f"Item {placement.item_id} is above the floor without a supporting top face",
                (placement.item_id,),
                placement.container_id,
            ))
        if support.exact_support_ratio + 1e-12 < support_threshold:
            issues.append(ValidationIssue(
                "INSUFFICIENT_SUPPORT_RATIO",
                f"Item {placement.item_id} exact support ratio {support.exact_support_ratio:.6f} is below {support_threshold:.6f}",
                (placement.item_id,),
                placement.container_id,
            ))
        if not support.center_supported:
            issues.append(ValidationIssue(
                "CENTER_NOT_SUPPORTED",
                f"Item {placement.item_id} base center is not supported",
                (placement.item_id,),
                placement.container_id,
            ))
        records.append(SupportRecord(
            placement.item_id,
            placement.container_id,
            support.is_on_floor,
            support.supporting_item_ids,
            support.support_area_mm2,
            support.base_area_mm2,
            support.exact_support_ratio,
            dense_count,
            dense_size,
            dense_count / dense_size,
            support.center_supported,
        ))
    return SupportValidation(
        ValidationResult(valid=not issues, issues=issues),
        tuple(records),
        support_threshold,
        dense_grid_x,
        dense_grid_y,
        orientation_profile,
    )
