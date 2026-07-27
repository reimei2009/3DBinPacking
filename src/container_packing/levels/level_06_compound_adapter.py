"""Shared compound-root adapter for all experimental Level 6 search engines."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any, Callable, TYPE_CHECKING

from ..algorithms.contracts import AlgorithmOutcome
from ..algorithms.orientation import fixed_orientation_provider
from ..schemas import Container, Item, Placement
from .level_06_compound_policy import build_level_06_compound_fixture_policy
from .nesting import NestingSettings, attributes_for_item
from .nesting_construction import NestingConstructionResult, construct_nesting_relations
from .nesting_engine import NestingRelation
from .nesting_runtime import (
    NestingRuntimeProjection,
    compound_to_external_item,
    project_nesting_compounds,
)

if TYPE_CHECKING:
    from .level_06_pipeline import ValidationBundle


CompoundSolver = Callable[..., AlgorithmOutcome]
CompoundValidator = Callable[[list[Item], list[Container], list[Placement], dict[str, Any], list[NestingRelation]], "ValidationBundle"]


@dataclass(frozen=True)
class Level06CompoundResult:
    outcome: AlgorithmOutcome
    item_count: int
    construction: NestingConstructionResult
    relations: tuple[NestingRelation, ...]
    placements: tuple[Placement, ...]
    projection: NestingRuntimeProjection | None
    validation: ValidationBundle | None


@dataclass(frozen=True)
class Level06CompoundAdapter:
    """Run one solver over fixed, preconstructed compound roots."""

    algorithm_id: str
    adapter_id: str
    solver: CompoundSolver
    validator: CompoundValidator | None = None

    def solve(
        self, items: list[Item], containers: list[Container], config: dict[str, Any]
    ) -> Level06CompoundResult:
        started_at = perf_counter()
        from .level_06_pipeline import nesting_rules, validate_level_06_bundle

        rules = nesting_rules(config)
        settings = NestingSettings.from_config(rules)
        virtual = _virtual_placements(items)
        construction = construct_nesting_relations(items, virtual, settings)
        attributes = {item.item_id: attributes_for_item(item) for item in items}
        virtual_projection = project_nesting_compounds(
            virtual,
            attributes,
            construction.relations,
            clearance_mm=settings.clearance_mm,
        )
        original_items = {item.item_id: item for item in items}
        compound_items = [
            compound_to_external_item(value, original_items[value.root_item_id])
            for value in virtual_projection.compounds
        ]
        solver_settings = dict(config)
        policy = build_level_06_compound_fixture_policy(compound_items, config)
        outcome = self.solver(
            compound_items,
            containers,
            solver_settings,
            policy=policy,
            orientation_provider=fixed_orientation_provider(),
        )
        outcome.metadata.update({
            "fixture_adapter": self.adapter_id,
            "compound_constructor": self.algorithm_id,
            "compound_relation_graph_mode": "fixed_preconstructed_relations",
            "compound_search_item_count": len(compound_items),
            "nesting_runtime_enabled": False,
            **construction.metadata(),
            "n_items": len(items),
            "compound_candidate_count": len(compound_items),
            "compound_geometry_model": "compound_root_effective_envelope_geometry_v1",
            **policy.metadata(),
        })
        if outcome.solve.status != "FEASIBLE":
            outcome.metadata["algorithm_runtime_seconds"] = perf_counter() - started_at
            return Level06CompoundResult(
                outcome, len(items), construction, (), (), None, None
            )

        expanded, relations = _expand_logical_members(
            items, outcome.placements, construction.relations
        )
        outcome.placements = expanded
        projection = project_nesting_compounds(
            expanded, attributes, relations, clearance_mm=settings.clearance_mm
        )
        validate = self.validator or validate_level_06_bundle
        validation = validate(items, containers, expanded, config, list(relations))
        outcome.metadata.update({
            "compound_validation_status": "VALID" if validation.result.valid else "INVALID",
            "nested_relation_count": len(relations),
            "algorithm_runtime_seconds": perf_counter() - started_at,
        })
        return Level06CompoundResult(
            outcome,
            len(items),
            construction,
            relations,
            tuple(expanded),
            projection,
            validation,
        )


def _virtual_placements(items: list[Item]) -> list[Placement]:
    return [
        Placement(
            item.item_id,
            "__nesting_relation_selection__",
            0.0,
            0.0,
            0.0,
            item.length_mm,
            item.width_mm,
            item.height_mm,
            item.weight_kg,
            "XYZ",
        )
        for item in items
    ]


def _expand_logical_members(
    items: list[Item],
    root_placements: list[Placement],
    relations: tuple[NestingRelation, ...],
) -> tuple[list[Placement], tuple[NestingRelation, ...]]:
    roots = {placement.item_id: placement for placement in root_placements}
    parent_by_child = {
        relation.child_item_id: relation.host_item_id for relation in relations
    }

    def root_id(item_id: str) -> str:
        current = item_id
        while current in parent_by_child:
            current = parent_by_child[current]
        return current

    expanded: list[Placement] = []
    for item in sorted(items, key=lambda value: value.item_id):
        root = roots[root_id(item.item_id)]
        expanded.append(Placement(
            item.item_id,
            root.container_id,
            root.x_mm,
            root.y_mm,
            root.z_mm,
            item.length_mm,
            item.width_mm,
            item.height_mm,
            item.weight_kg,
            "XYZ",
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
