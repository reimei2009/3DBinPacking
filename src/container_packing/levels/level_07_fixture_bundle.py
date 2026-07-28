"""Independent composition of Level 6 evidence with Level 7 balance evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..data_loader import load_config
from ..runtime.project import find_project_root
from ..schemas import Container, Item, Placement, ValidationIssue, ValidationResult
from .level_06_pipeline import nesting_rules, validate_level_06_bundle
from .level_07_validation import validate_container_balance
from .nesting import NestingSettings, attributes_for_item
from .nesting_engine import NestingRelation
from .nesting_runtime import (
    compound_to_external_item,
    compound_to_external_placement,
    project_nesting_compounds,
)
from .pipeline import ValidationBundle


def balance_rules(config: dict[str, Any]) -> dict[str, Any]:
    """Resolve the explicit Level 7 balance profile."""
    value = config.get("balance", {})
    if "contract_version" in value:
        return value
    rules_file = value.get("rules_file")
    if not rules_file:
        raise ValueError("Level 7 balance validation requires balance.rules_file")
    root = find_project_root(__file__)
    path = Path(str(rules_file))
    loaded = load_config(path if path.is_absolute() else root / path)
    config["balance"] = {**loaded, "rules_file": str(rules_file)}
    return config["balance"]


def validate_level_07_fixture_bundle(
    items: list[Item],
    containers: list[Container],
    placements: list[Placement],
    config: dict[str, Any],
    relations: list[NestingRelation] | None,
) -> ValidationBundle:
    """Add independent compound-root COG evidence after Level 6 validation.

    Relations are explicit fixture input. This makes the Level 6 relation graph
    and the external compound projection identical for inherited validation and
    the Level 7 COG calculation, while both validators remain independent.
    """
    inherited = validate_level_06_bundle(items, containers, placements, config, relations)
    rules = balance_rules(config)
    if not inherited.result.valid:
        return _with_unavailable_balance(inherited, rules)

    try:
        nesting = nesting_rules(config)
        settings = NestingSettings.from_config(nesting)
        attributes = {item.item_id: attributes_for_item(item) for item in items}
        resolved_relations = relations
        if resolved_relations is None:
            resolved_relations = [
                NestingRelation(
                    str(row["host_item_id"]), str(row["child_item_id"]), str(row["container_id"])
                )
                for row in inherited.solution_tables["nesting_relations.csv"]
            ]
        projection = project_nesting_compounds(
            placements, attributes, resolved_relations, clearance_mm=settings.clearance_mm
        )
        item_by_id = {item.item_id: item for item in items}
        compound_items = [
            compound_to_external_item(value, item_by_id[value.root_item_id])
            for value in projection.compounds
        ]
        compound_placements = [
            compound_to_external_placement(value) for value in projection.compounds
        ]
    except (KeyError, ValueError) as exc:
        issue = ValidationIssue("BALANCE_COMPOUND_PROJECTION_INVALID", str(exc))
        return _merge_bundle(inherited, ValidationResult(False, [issue]), (), rules)

    balance = validate_container_balance(
        compound_items, containers, compound_placements, rules,
        balance_tolerance=float(config.get("validation", {}).get("balance_tolerance", 1e-9)),
    )
    return _merge_bundle(inherited, balance.result, balance.records, rules)


def _with_unavailable_balance(
    inherited: ValidationBundle, rules: dict[str, Any]
) -> ValidationBundle:
    document = {
        "valid": False,
        "model": "mass_weighted_item_geometric_center_v1",
        "records": [],
        "violations": [],
        "status": "not_evaluated_due_to_invalid_level_06_bundle",
    }
    return ValidationBundle(
        inherited.result,
        solution_tables=dict(inherited.solution_tables),
        validation_documents={**inherited.validation_documents, "balance_validation.json": document},
        solution_payload_extra=dict(inherited.solution_payload_extra),
        scene_item_metadata=dict(inherited.scene_item_metadata),
        extra_report_lines=[*inherited.extra_report_lines, "- Level 7 balance: not evaluated because inherited Level 6 validation failed."],
        metadata={
            **inherited.metadata,
            "level_07_balance_validation": True,
            "level_07_fixture_validation_only": True,
            "center_of_mass_model": "mass_weighted_item_geometric_center_v1",
            "balance_validation_status": "NOT_EVALUATED",
            "balance_profile": rules["balance_profile"]["mode"],
        },
    )


def _merge_bundle(
    inherited: ValidationBundle,
    balance_result: ValidationResult,
    records,
    rules: dict[str, Any],
) -> ValidationBundle:
    combined_issues = [*inherited.result.issues, *balance_result.issues]
    combined = ValidationResult(not combined_issues, combined_issues)
    balance_payload = {
        "valid": balance_result.valid,
        "model": "mass_weighted_item_geometric_center_v1",
        "records": [value.to_dict() for value in records],
        "violations": [
            {
                "code": value.code,
                "message": value.message,
                "item_ids": list(value.item_ids),
                "container_id": value.container_id,
            }
            for value in balance_result.issues
        ],
    }
    balanced_count = sum(value.balanced for value in records)
    return ValidationBundle(
        combined,
        solution_tables={
            **inherited.solution_tables,
            "center_of_mass.csv": [value.to_dict() for value in records],
        },
        validation_documents={
            **inherited.validation_documents,
            "balance_validation.json": balance_payload,
        },
        solution_payload_extra={
            **inherited.solution_payload_extra,
            "balance": {"model": balance_payload["model"], "records": balance_payload["records"]},
        },
        scene_item_metadata=dict(inherited.scene_item_metadata),
        extra_report_lines=[
            *inherited.extra_report_lines,
            f"- Balanced compound-root containers: {balanced_count}/{len(records)}",
        ],
        metadata={
            **inherited.metadata,
            "level_07_balance_validation": True,
            "level_07_fixture_validation_only": True,
            "center_of_mass_model": "mass_weighted_item_geometric_center_v1",
            "balance_profile": rules["balance_profile"]["mode"],
            "balance_validation_status": "VALID" if balance_result.valid else "INVALID",
            "balanced_container_count": balanced_count,
            "unbalanced_container_count": len(records) - balanced_count,
        },
    )
