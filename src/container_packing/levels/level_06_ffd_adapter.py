"""Fixture-only nesting-aware adapter around the shared Extreme-Point FFD.

The adapter first decides declared nesting relations, projects each chain to one
external compound, packs those compounds, and finally expands logical members
for the independent Level 6 compound-validation bundle. It is the single
experimentally registered Level 6 solver, not a practical default.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable, TYPE_CHECKING

from ..algorithms.contracts import AlgorithmOutcome
from ..algorithms.heuristics.extreme_point_ffd import solve as solve_extreme_point_ffd
from ..algorithms.orientation import fixed_orientation_provider
from ..schemas import Container, Item, Placement
from .level_06_compound_policy import build_level_06_compound_fixture_policy
from .nesting import NestingSettings, attributes_for_item
from .nesting_construction import NestingConstructionResult, construct_nesting_relations
from .nesting_engine import NestingRelation
from .nesting_runtime import NestingRuntimeProjection, project_nesting_compounds

if TYPE_CHECKING:
    from .level_06_pipeline import ValidationBundle


@dataclass(frozen=True)
class Level06NestingFfdFixtureResult:
    """Result of a fixture-only compound construction and its final validation."""

    outcome: AlgorithmOutcome
    item_count: int
    construction: NestingConstructionResult
    relations: tuple[NestingRelation, ...]
    placements: tuple[Placement, ...]
    projection: NestingRuntimeProjection | None
    validation: ValidationBundle | None


CompoundConstructor = Callable[..., AlgorithmOutcome]


def solve_nesting_aware_ffd_fixture(
    items: list[Item],
    containers: list[Container],
    config: dict[str, Any],
) -> Level06NestingFfdFixtureResult:
    """Run the experimental FFD constructor through the shared adapter."""
    return solve_nesting_aware_compound_fixture(
        items,
        containers,
        config,
        constructor=solve_extreme_point_ffd,
        algorithm_id="extreme_point_ffd_nesting_fixture",
        adapter_id="level_06_nesting_aware_ffd_compound_v1",
    )


def solve_nesting_aware_compound_fixture(
    items: list[Item],
    containers: list[Container],
    config: dict[str, Any],
    *,
    constructor: CompoundConstructor,
    algorithm_id: str,
    adapter_id: str,
) -> Level06NestingFfdFixtureResult:
    """Pack compound roots with FFD and validate their expanded logical members.

    Relation selection runs against a neutral, common-container representation
    because actual containers are selected later by FFD.  Once roots are packed,
    each child inherits its root's external container and coordinates.  This is
    the declared Level 6 logical-member representation, not raw overlapping
    external geometry.
    """
    started_at = perf_counter()
    # The pipeline owns config resolution and independent validation. Delaying
    # this import keeps the registered pipeline from forming an import cycle.
    from .level_06_pipeline import nesting_rules, validate_level_06_bundle

    rules = nesting_rules(config)
    settings = NestingSettings.from_config(rules)
    virtual = _virtual_placements(items)
    construction = construct_nesting_relations(items, virtual, settings)
    attributes = {item.item_id: attributes_for_item(item) for item in items}
    virtual_projection = project_nesting_compounds(
        virtual, attributes, construction.relations, clearance_mm=settings.clearance_mm
    )
    compound_items = _compound_items(items, virtual_projection)
    solver_settings = dict(config)
    policy = build_level_06_compound_fixture_policy(compound_items, config)
    outcome = constructor(
        compound_items,
        containers,
        solver_settings,
        policy=policy,
        orientation_provider=fixed_orientation_provider(),
    )
    outcome.metadata.update({
        "fixture_adapter": adapter_id,
        "compound_constructor": algorithm_id,
        "nesting_runtime_enabled": False,
        **construction.metadata(),
        "n_items": len(items),
        "compound_candidate_count": len(compound_items),
        "compound_geometry_model": "compound_root_effective_envelope_geometry_v1",
        **policy.metadata(),
    })
    if outcome.solve.status != "FEASIBLE":
        outcome.metadata["algorithm_runtime_seconds"] = perf_counter() - started_at
        return Level06NestingFfdFixtureResult(
            outcome, len(items), construction, (), (), None, None
        )
    expanded, relations = _expand_logical_members(
        items, outcome.placements, construction.relations
    )
    # The generic runtime expects one canonical placement per original item.
    # Compound roots are an internal construction representation only.
    outcome.placements = expanded
    projection = project_nesting_compounds(
        expanded, attributes, relations, clearance_mm=settings.clearance_mm
    )
    validation = validate_level_06_bundle(items, containers, expanded, config, list(relations))
    outcome.metadata.update({
        "compound_validation_status": "VALID" if validation.result.valid else "INVALID",
        "nested_relation_count": len(relations),
        "algorithm_runtime_seconds": perf_counter() - started_at,
    })
    return Level06NestingFfdFixtureResult(
        outcome, len(items), construction, relations, tuple(expanded), projection, validation
    )


def _virtual_placements(items: list[Item]) -> list[Placement]:
    return [
        Placement(
            item.item_id, "__nesting_relation_selection__", 0.0, 0.0, 0.0,
            item.length_mm, item.width_mm, item.height_mm, item.weight_kg, "XYZ",
        )
        for item in items
    ]


def _compound_items(
    items: list[Item], projection: NestingRuntimeProjection
) -> list[Item]:
    item_by_id = {item.item_id: item for item in items}
    return [
        Item(
            compound.root_item_id,
            compound.length_mm,
            compound.width_mm,
            compound.effective_height_mm,
            compound.external_weight_kg,
            level1_order=item_by_id[compound.root_item_id].level1_order,
            source={
                **item_by_id[compound.root_item_id].source,
                "compound_member_item_ids": ",".join(compound.member_item_ids),
                "compound_projection": "level_06_external_root",
            },
        )
        for compound in projection.compounds
    ]


def _expand_logical_members(
    items: list[Item],
    root_placements: list[Placement],
    relations: tuple[NestingRelation, ...],
) -> tuple[list[Placement], tuple[NestingRelation, ...]]:
    item_by_id = {item.item_id: item for item in items}
    roots = {placement.item_id: placement for placement in root_placements}
    parent_by_child = {relation.child_item_id: relation.host_item_id for relation in relations}

    def root_id(item_id: str) -> str:
        current = item_id
        while current in parent_by_child:
            current = parent_by_child[current]
        return current

    expanded: list[Placement] = []
    for item in sorted(items, key=lambda value: value.item_id):
        root = roots[root_id(item.item_id)]
        expanded.append(Placement(
            item.item_id, root.container_id, root.x_mm, root.y_mm, root.z_mm,
            item.length_mm, item.width_mm, item.height_mm, item.weight_kg, "XYZ",
        ))
    resolved_relations = tuple(sorted((
        NestingRelation(
            relation.host_item_id,
            relation.child_item_id,
            roots[root_id(relation.host_item_id)].container_id,
        )
        for relation in relations
    ), key=lambda value: (value.host_item_id, value.child_item_id)))
    return expanded, resolved_relations
