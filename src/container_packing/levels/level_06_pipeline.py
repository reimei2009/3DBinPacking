"""Fixture-only Level 6 validation composition over the active Level 5 contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..data_loader import load_config
from ..runtime.project import find_project_root
from ..schemas import Container, Item, Placement, ValidationResult
from .level_04_pipeline import _rules as stackability_rules
from .level_04_validation import validate_stack_graph
from .level_05_pipeline import load_bearing_rules
from .level_05_validation import validate_load_bearing
from .level_06_compound_validation import validate_compound_geometry
from .level_06_validation import Level06NestingValidation, validate_nesting
from .nesting import NestingSettings
from .nesting_construction import construct_nesting_relations
from .nesting_engine import NestingRelation
from .nesting_runtime import compound_to_external_placement
from .pipeline import ValidationBundle
from .pipeline import LevelRuntimeStrategy, run_configured_level
from .level_03_preprocessing import validate_instance
from .level_06_candidate_contract import load_runtime_candidate_contract
from .level_06_ffd_adapter import solve_nesting_aware_ffd_fixture
from .stackability import (
    StackabilitySettings,
    attributes_for_item as stackability_attributes_for_item,
    infer_parent_relations,
    report_lines as stack_report_lines,
    scene_item_metadata as stack_scene_item_metadata,
    solution_payload as stack_solution_payload,
)
from .support_validation import SupportRecord, SupportValidation


def nesting_rules(config: dict[str, Any]) -> dict[str, Any]:
    """Resolve one explicit Level 6 nesting contract without a runtime registry."""
    value = config.get("nesting", {})
    if "contract_version" in value:
        return value
    rules_file = value.get("rules_file")
    if not rules_file:
        raise ValueError("Level 6 fixture validation requires nesting.rules_file")
    root = find_project_root(__file__)
    path = Path(str(rules_file))
    loaded = load_config(path if path.is_absolute() else root / path)
    config["nesting"] = {**loaded, "rules_file": str(rules_file)}
    return config["nesting"]


def validate_level_06_bundle(
    items: list[Item],
    containers: list[Container],
    placements: list[Placement],
    config: dict[str, Any],
    relations: list[NestingRelation] | None = None,
) -> ValidationBundle:
    """Validate a fixture through compound geometry, stackability, and load transfer.

    This API is intentionally fixture-only: callers supply nesting relations
    explicitly. Raw nested child boxes never enter external geometry, support,
    stackability, or load-transfer checks; those checks receive compounds.
    """
    rules = nesting_rules(config)
    settings = NestingSettings.from_config(rules)
    construction_metadata: dict[str, Any] = {}
    if relations is None:
        construction = construct_nesting_relations(items, placements, settings)
        relations = list(construction.relations)
        construction_metadata = construction.metadata()
    nesting_details = validate_nesting(
        items, placements, relations, clearance_mm=settings.clearance_mm
    )
    nesting_records = [record.to_dict() for record in nesting_details.records]
    nesting_relations = [relation.to_dict() for relation in nesting_details.relations]
    if not nesting_details.result.valid:
        return _invalid_bundle(rules, nesting_details, nesting_records, nesting_relations)

    support = config["support"]
    validation = config.get("validation", {})
    compound = validate_compound_geometry(
        items, containers, placements, relations, rules,
        support_threshold=float(support["threshold"]),
        support_epsilon_mm=float(support["epsilon_mm"]),
        coordinate_tolerance_mm=float(validation.get("coordinate_tolerance_mm", 1e-4)),
    )
    if compound.projection is None:
        return _invalid_bundle(
            rules, nesting_details, nesting_records, nesting_relations,
            compound_document=compound.payload(), compound_issues=compound.result,
        )
    compound_items = _compound_items(items, compound.projection.compounds)
    compound_placements = [
        compound_to_external_placement(value) for value in compound.projection.compounds
    ]
    compound_support = _support_evidence(compound, float(support["threshold"]))
    stack_rules = stackability_rules(config)
    stack_settings = StackabilitySettings.from_config(stack_rules)
    stack_attributes = {
        item.item_id: stackability_attributes_for_item(item, stack_settings)
        for item in compound_items
    }
    stack_relations = infer_parent_relations(
        compound_placements, stack_attributes, epsilon_mm=float(support["epsilon_mm"])
    )
    stack = validate_stack_graph(
        compound_items, compound_placements, stack_relations, stack_rules,
        support_validation=compound_support,
        support_epsilon_mm=float(support["epsilon_mm"]),
    )
    load_rules = load_bearing_rules(config)
    load = validate_load_bearing(
        compound_items, compound_placements, load_rules,
        epsilon_mm=float(support["epsilon_mm"]),
        load_tolerance_kg=float(validation.get("load_tolerance_kg", 1e-6)),
    )
    issues = [*stack.result.issues, *load.result.issues]
    combined = ValidationResult(not issues, issues)
    stack_records = [record.to_dict() for record in stack.stack_records]
    load_records = [record.to_dict() for record in load.records]
    load_edges = [edge.to_dict() for edge in load.edges]
    compound_rows = [value.to_dict() for value in compound.projection.compounds]
    scene_metadata = stack_scene_item_metadata(stack.stack_records)
    for record in nesting_details.records:
        scene_metadata.setdefault(record.item_id, {}).update({
            "nesting_root_item_id": record.root_item_id,
            "nesting_host_item_id": record.host_item_id,
            "nesting_depth": record.nesting_depth,
            "nesting_chain_effective_height_mm": record.chain_effective_height_mm,
            "nesting_vertical_contribution_height_mm": record.vertical_contribution_height_mm,
        })
    load_metadata = _load_metadata(load)
    support_metadata = _compound_support_metadata(
        compound.support_records, float(support["threshold"])
    )
    metadata = {
        **_nesting_metadata(
            rules,
            nesting_details,
            runtime_enabled=bool(config.get("model", {}).get("enforce_nesting", False)),
        ),
        **construction_metadata,
        "compound_geometry_model": "compound_root_effective_envelope_geometry_v1",
        "compound_count": len(compound.projection.compounds),
        "stackability_contract_version": stack_rules["contract_version"],
        "load_bearing_contract_version": load_rules["contract_version"],
        "load_bearing_capacity_profile": load_rules["capacity_profile"]["mode"],
        "load_transfer_model": "compound_weight_through_root_external_contacts",
        **support_metadata,
        **load_metadata,
    }
    return ValidationBundle(
        combined,
        solution_tables={
            "nesting_relations.csv": nesting_relations,
            "nesting_height.csv": nesting_records,
            "nesting_compounds.csv": compound_rows,
            "compound_support.csv": [record.to_dict() for record in compound.support_records],
            "stacks.csv": stack_records,
            "load_bearing.csv": load_records,
            "load_transfer.csv": load_edges,
        },
        validation_documents={
            "nesting_validation.json": nesting_details.payload(),
            "compound_geometry_validation.json": compound.payload(),
            "stack_validation.json": stack.payload(),
            "load_bearing_validation.json": load.payload(),
        },
        solution_payload_extra={
            "nesting": {
                "model": "compound_root_effective_envelope_geometry_v1",
                "relations": nesting_relations,
                "records": nesting_records,
                "compounds": compound_rows,
            },
            "stackability": stack_solution_payload(stack.stack_records),
            "load_bearing": {
                "model": "compound_weight_through_root_external_contacts",
                "records": load_records,
                "edges": load_edges,
            },
        },
        scene_item_metadata=scene_metadata,
        extra_report_lines=[
            *stack_report_lines(stack.stack_records),
            f"- Declared nesting relations: {metadata['nesting_relation_count']}",
            f"- Compound envelopes: {metadata['compound_count']}",
            f"- Maximum nesting depth: {metadata['maximum_nesting_depth']}",
            f"- Load-transfer edges: {metadata['load_transfer_edge_count']}",
            "- External geometry and load transfer use compound roots; internal nesting forces are inactive.",
        ],
        metadata=metadata,
    )


def _nesting_metadata(
    rules: dict[str, Any],
    details: Level06NestingValidation,
    *,
    runtime_enabled: bool = False,
) -> dict[str, Any]:
    return {
        "nesting_contract_version": rules["contract_version"],
        "nesting_data_status": "explicit_metadata_fixture_validation_only",
        "nesting_validation_model": "explicit_nesting_chain_effective_height_v1",
        "nesting_relation_count": len(details.relations),
        "maximum_nesting_depth": max(
            (record.nesting_depth for record in details.records), default=0
        ),
        "nesting_runtime_enabled": runtime_enabled,
    }


def _compound_items(items: list[Item], compounds) -> list[Item]:
    original = {item.item_id: item for item in items}
    values: list[Item] = []
    for compound in compounds:
        root = original[compound.root_item_id]
        values.append(Item(
            compound.root_item_id,
            compound.length_mm,
            compound.width_mm,
            compound.effective_height_mm,
            compound.external_weight_kg,
            level1_order=root.level1_order,
            source={
                **root.source,
                "compound_member_item_ids": ",".join(compound.member_item_ids),
                "compound_projection": "level_06_external_root",
            },
        ))
    return values


def _support_evidence(compound, threshold: float) -> SupportValidation:
    records = tuple(
        SupportRecord(
            record.root_item_id,
            record.container_id,
            record.is_on_floor,
            record.supporting_root_item_ids,
            record.support_area_mm2,
            record.base_area_mm2,
            record.exact_support_ratio,
            0,
            0,
            0.0,
            record.center_supported,
        )
        for record in compound.support_records
    )
    return SupportValidation(
        compound.result, records, threshold, 0, 0, "compound_root_effective_envelope"
    )


def _load_metadata(details) -> dict[str, Any]:
    ratios = [
        record.load_utilization_ratio for record in details.records
        if record.load_utilization_ratio is not None
    ]
    margins = [record.safety_margin_kg for record in details.records]
    return {
        "maximum_load_utilization_ratio": max(ratios, default=0.0),
        "minimum_load_safety_margin_kg": min(margins, default=0.0),
        "fragile_item_count": sum(record.is_fragile for record in details.records),
        "overloaded_item_count": sum(
            record.load_above_kg > record.max_supported_weight_kg
            for record in details.records
        ),
        "load_transfer_edge_count": len(details.edges),
    }


def _compound_support_metadata(records, threshold: float) -> dict[str, Any]:
    return {
        "support_enabled": True,
        "support_threshold": threshold,
        "minimum_exact_support_ratio": min(
            (record.exact_support_ratio for record in records), default=1.0
        ),
        "all_centers_supported": all(record.center_supported for record in records),
    }


def _invalid_bundle(
    rules: dict[str, Any],
    nesting: Level06NestingValidation,
    nesting_records: list[dict[str, Any]],
    nesting_relations: list[dict[str, Any]],
    *,
    compound_document: dict[str, Any] | None = None,
    compound_issues: ValidationResult | None = None,
) -> ValidationBundle:
    result = nesting.result if compound_issues is None else compound_issues
    documents = {"nesting_validation.json": nesting.payload()}
    if compound_document is not None:
        documents["compound_geometry_validation.json"] = compound_document
    return ValidationBundle(
        result,
        solution_tables={
            "nesting_relations.csv": nesting_relations,
            "nesting_height.csv": nesting_records,
        },
        validation_documents=documents,
        solution_payload_extra={
            "nesting": {
                "model": "compound_root_effective_envelope_geometry_v1",
                "relations": nesting_relations,
                "records": nesting_records,
            },
        },
        metadata=_nesting_metadata(rules, nesting),
    )


def _guard(config: dict[str, Any]) -> None:
    candidate = load_runtime_candidate_contract(config)
    if config.get("project", {}).get("level_id") != "level_06":
        raise ValueError("Experimental Level 6 runtime requires project.level_id='level_06'")
    if config.get("project", {}).get("algorithm_id") != candidate.algorithm_id:
        raise ValueError("Experimental Level 6 runtime requires its frozen candidate algorithm")
    if not bool(config.get("model", {}).get("enforce_nesting", False)):
        raise ValueError("Experimental Level 6 runtime requires model.enforce_nesting=true")
    NestingSettings.from_config(nesting_rules(config))


def _execute(algorithm_id: str, items, containers, settings):
    if algorithm_id != "extreme_point_ffd_nesting_fixture":
        raise ValueError("Experimental Level 6 exposes only extreme_point_ffd_nesting_fixture")
    return solve_nesting_aware_ffd_fixture(items, containers, settings).outcome


STRATEGY = LevelRuntimeStrategy(
    level_number=6,
    execute=_execute,
    validate_instance=lambda items, containers, expected: validate_instance(
        items, containers, expected_items=expected
    ),
    validate_solution=validate_level_06_bundle,
    guard_config=_guard,
    active_constraints=(
        "compound_boundaries", "compound_payload", "compound_non_overlap",
        "exact_base_support", "base_center_support", "stackability_same_group",
        "maximum_stack_layers", "recursive_static_load_transfer",
        "maximum_supported_weight", "explicit_nesting_relations",
    ),
    inactive_constraints=(
        "vertical_axis_rotation", "internal_nesting_load_transfer", "pressure",
        "contact_moments", "dynamic_load", "full_physical_stability",
        "nesting_aware_best_fit", "nesting_aware_metaheuristics",
    ),
    metadata_defaults={
        "solution_claim": (
            "Experimental compound-root nesting solution validated for geometry, support, "
            "stackability and static external load transfer under research assumptions."
        ),
        "experimental_runtime": True,
        "runtime_promotion_status": "experimental_registered_not_default",
        "rotation_enabled": False,
        "support_enabled": True,
        "stackability_enabled": True,
        "load_bearing_enabled": True,
        "load_transfer_enabled": True,
        "nesting_runtime_enabled": True,
        "physical_stability_claim": False,
        "nesting_scope": "explicit_declared_compound_root_fixture_candidate",
    },
    algorithm_roles={"extreme_point_ffd_nesting_fixture": "experimental_candidate"},
)


def run_from_config(
    config_path: str | Path,
    *,
    item_count: int | None = None,
    container_count: int | None = None,
    write_outputs: bool = True,
    level_id: str = "level_06",
    algorithm_id: str = "extreme_point_ffd_nesting_fixture",
    environment: str = "local",
    random_seed: int | None = None,
    algorithm_parameters: dict[str, Any] | None = None,
    config_overrides: dict[str, Any] | None = None,
    item_selection_strategy: str | None = None,
    item_selection_seed: int | None = None,
):
    return run_configured_level(
        config_path,
        strategy=STRATEGY,
        item_count=item_count,
        container_count=container_count,
        write_outputs=write_outputs,
        level_id=level_id,
        algorithm_id=algorithm_id,
        environment=environment,
        random_seed=random_seed,
        algorithm_parameters=algorithm_parameters,
        config_overrides=config_overrides,
        item_selection_strategy=item_selection_strategy,
        item_selection_seed=item_selection_seed,
    )
