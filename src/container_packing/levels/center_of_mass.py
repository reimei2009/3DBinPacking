"""Pure Level 7 mass-weighted container center-of-mass evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

from ..schemas import Container, Placement
from .load_balance import (
    ContainerBalanceAttributes,
    resolve_container_balance_attributes,
)


class CenterOfMassError(ValueError):
    """Raised when canonical placement data cannot form a COG calculation."""


@dataclass(frozen=True)
class CenterOfMassRecord:
    """Independent per-used-container Level 7 COG evidence."""

    container_id: str
    item_count: int
    total_weight_kg: float
    center_x_mm: float
    center_y_mm: float
    center_z_mm: float
    longitudinal_ratio: float
    lateral_ratio: float
    target_longitudinal_ratio: float
    target_lateral_ratio: float
    signed_longitudinal_offset_ratio: float
    signed_lateral_offset_ratio: float
    absolute_longitudinal_offset_ratio: float
    absolute_lateral_offset_ratio: float
    max_longitudinal_offset_ratio: float
    max_lateral_offset_ratio: float
    longitudinal_balanced: bool
    lateral_balanced: bool
    balance_profile_source: str

    @property
    def balanced(self) -> bool:
        return self.longitudinal_balanced and self.lateral_balanced

    def to_dict(self) -> dict[str, Any]:
        return {
            "container_id": self.container_id,
            "item_count": self.item_count,
            "total_weight_kg": self.total_weight_kg,
            "center_x_mm": self.center_x_mm,
            "center_y_mm": self.center_y_mm,
            "center_z_mm": self.center_z_mm,
            "longitudinal_ratio": self.longitudinal_ratio,
            "lateral_ratio": self.lateral_ratio,
            "target_longitudinal_ratio": self.target_longitudinal_ratio,
            "target_lateral_ratio": self.target_lateral_ratio,
            "signed_longitudinal_offset_ratio": self.signed_longitudinal_offset_ratio,
            "signed_lateral_offset_ratio": self.signed_lateral_offset_ratio,
            "absolute_longitudinal_offset_ratio": self.absolute_longitudinal_offset_ratio,
            "absolute_lateral_offset_ratio": self.absolute_lateral_offset_ratio,
            "max_longitudinal_offset_ratio": self.max_longitudinal_offset_ratio,
            "max_lateral_offset_ratio": self.max_lateral_offset_ratio,
            "longitudinal_balanced": self.longitudinal_balanced,
            "lateral_balanced": self.lateral_balanced,
            "balanced": self.balanced,
            "balance_profile_source": self.balance_profile_source,
        }


@dataclass(frozen=True)
class CenterOfMassEvaluation:
    records: tuple[CenterOfMassRecord, ...]


def evaluate_center_of_mass(
    placements: list[Placement] | tuple[Placement, ...],
    containers: list[Container] | tuple[Container, ...],
    balance_config: dict[str, Any],
    *,
    tolerance: float = 1e-9,
) -> CenterOfMassEvaluation:
    """Compute COG only from canonical placements and versioned profile data."""
    if tolerance < 0 or not isfinite(tolerance):
        raise ValueError("Center-of-mass tolerance must be finite and non-negative")
    attributes = resolve_container_balance_attributes(containers, balance_config)
    containers_by_id = {value.container_id: value for value in containers}
    grouped: dict[str, list[Placement]] = {}
    for placement in placements:
        if placement.container_id not in containers_by_id:
            raise CenterOfMassError(
                f"Center-of-mass placement references unknown container {placement.container_id}"
            )
        _validate_placement(placement)
        grouped.setdefault(placement.container_id, []).append(placement)

    records = tuple(
        _record_for_container(
            container_id,
            grouped[container_id],
            containers_by_id[container_id],
            attributes[container_id],
            tolerance,
        )
        for container_id in sorted(grouped)
    )
    return CenterOfMassEvaluation(records)


def _record_for_container(
    container_id: str,
    placements: list[Placement],
    container: Container,
    attributes: ContainerBalanceAttributes,
    tolerance: float,
) -> CenterOfMassRecord:
    total_weight = sum(value.weight_kg for value in placements)
    if not isfinite(total_weight) or total_weight <= 0:
        raise CenterOfMassError(
            f"Container {container_id} requires a positive finite total placement weight"
        )
    center_x = sum(value.weight_kg * (value.x_mm + value.length_mm / 2.0) for value in placements) / total_weight
    center_y = sum(value.weight_kg * (value.y_mm + value.width_mm / 2.0) for value in placements) / total_weight
    center_z = sum(value.weight_kg * (value.z_mm + value.height_mm / 2.0) for value in placements) / total_weight
    longitudinal_ratio = center_x / container.length_mm
    lateral_ratio = center_y / container.width_mm
    signed_longitudinal = longitudinal_ratio - attributes.target_longitudinal_ratio
    signed_lateral = lateral_ratio - attributes.target_lateral_ratio
    absolute_longitudinal = abs(signed_longitudinal)
    absolute_lateral = abs(signed_lateral)
    return CenterOfMassRecord(
        container_id, len(placements), total_weight, center_x, center_y, center_z,
        longitudinal_ratio, lateral_ratio,
        attributes.target_longitudinal_ratio, attributes.target_lateral_ratio,
        signed_longitudinal, signed_lateral, absolute_longitudinal, absolute_lateral,
        attributes.max_longitudinal_offset_ratio, attributes.max_lateral_offset_ratio,
        absolute_longitudinal <= attributes.max_longitudinal_offset_ratio + tolerance,
        absolute_lateral <= attributes.max_lateral_offset_ratio + tolerance,
        attributes.balance_profile_source,
    )


def _validate_placement(placement: Placement) -> None:
    values = {
        "weight_kg": placement.weight_kg,
        "x_mm": placement.x_mm,
        "y_mm": placement.y_mm,
        "z_mm": placement.z_mm,
        "length_mm": placement.length_mm,
        "width_mm": placement.width_mm,
        "height_mm": placement.height_mm,
    }
    for field, value in values.items():
        if not isfinite(value):
            raise CenterOfMassError(f"Placement {placement.item_id} has non-finite {field}")
    if placement.weight_kg <= 0:
        raise CenterOfMassError(f"Placement {placement.item_id} requires a positive weight_kg")
    for field in ("length_mm", "width_mm", "height_mm"):
        if values[field] <= 0:
            raise CenterOfMassError(f"Placement {placement.item_id} requires a positive {field}")
