"""Pure external compound projection for the designed, inactive Level 6 runtime."""

from __future__ import annotations

from dataclasses import dataclass

from ..schemas import Placement
from .nesting import NestingAttributes
from .nesting_engine import NestingEvaluation, NestingRelation, evaluate_nesting


@dataclass(frozen=True)
class NestingCompoundProjection:
    """One externally visible envelope for a root and all of its nested members."""

    root_item_id: str
    container_id: str
    member_item_ids: tuple[str, ...]
    x_mm: float
    y_mm: float
    z_mm: float
    length_mm: float
    width_mm: float
    effective_height_mm: float
    external_weight_kg: float
    orientation_code: str

    def to_dict(self) -> dict[str, object]:
        return {
            "root_item_id": self.root_item_id,
            "container_id": self.container_id,
            "member_item_ids": list(self.member_item_ids),
            "x_mm": self.x_mm,
            "y_mm": self.y_mm,
            "z_mm": self.z_mm,
            "length_mm": self.length_mm,
            "width_mm": self.width_mm,
            "effective_height_mm": self.effective_height_mm,
            "external_weight_kg": self.external_weight_kg,
            "orientation_code": self.orientation_code,
        }


@dataclass(frozen=True)
class NestingRuntimeProjection:
    """Canonical projection consumed by a future nesting-aware feasibility policy."""

    evaluation: NestingEvaluation
    compounds: tuple[NestingCompoundProjection, ...]


def compound_to_external_placement(compound: NestingCompoundProjection) -> Placement:
    """Build the external envelope consumed by future compound constraints."""
    return Placement(
        compound.root_item_id,
        compound.container_id,
        compound.x_mm,
        compound.y_mm,
        compound.z_mm,
        compound.length_mm,
        compound.width_mm,
        compound.effective_height_mm,
        compound.external_weight_kg,
        compound.orientation_code,
    )


def project_nesting_compounds(
    placements: list[Placement] | tuple[Placement, ...],
    attributes: dict[str, NestingAttributes],
    relations: list[NestingRelation] | tuple[NestingRelation, ...],
    *,
    clearance_mm: float = 0.0,
) -> NestingRuntimeProjection:
    """Project explicit nesting chains into external root envelopes.

    This is a design-time primitive only.  It neither alters ``Placement`` nor
    runs boundary, overlap, support, stackability, or load-bearing checks.
    A future Level 6 policy must apply those checks to returned compounds,
    while preserving all item weights in ``external_weight_kg``.
    """
    evaluation = evaluate_nesting(
        placements, attributes, relations, clearance_mm=clearance_mm
    )
    placement_by_id = {placement.item_id: placement for placement in placements}
    records_by_root: dict[str, list] = {}
    for record in evaluation.records:
        records_by_root.setdefault(record.root_item_id, []).append(record)
    compounds: list[NestingCompoundProjection] = []
    for root_item_id, records in records_by_root.items():
        root = placement_by_id[root_item_id]
        ordered = sorted(records, key=lambda value: (value.nesting_depth, value.item_id))
        compounds.append(NestingCompoundProjection(
            root_item_id=root_item_id,
            container_id=root.container_id,
            member_item_ids=tuple(value.item_id for value in ordered),
            x_mm=root.x_mm,
            y_mm=root.y_mm,
            z_mm=root.z_mm,
            length_mm=root.length_mm,
            width_mm=root.width_mm,
            effective_height_mm=max(value.chain_effective_height_mm for value in ordered),
            external_weight_kg=sum(placement_by_id[value.item_id].weight_kg for value in ordered),
            orientation_code=root.orientation_code,
        ))
    return NestingRuntimeProjection(
        evaluation,
        tuple(sorted(compounds, key=lambda value: value.root_item_id)),
    )
