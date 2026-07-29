"""Isolated writer for deterministic Level 8 sequential fixture artifacts."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable

from ..schemas import Item, Placement, ValidationIssue, ValidationResult
from .level_08_sequential_planner import (
    SimulationPlan,
    simulation_metrics,
    stop_summary_rows,
    validate_deterministic_plan,
)
from .level_08_simulation_contract import SequentialSimulationSettings
from .unloading import delivery_attributes_for_item


def write_sequential_fixture_artifacts(
    run_dir: Path, plan: SimulationPlan, items: Iterable[Item], placements: Iterable[Placement], settings: SequentialSimulationSettings
) -> dict[str, Path]:
    """Write the complete deterministic sequential evidence bundle."""
    if not run_dir.is_dir():
        raise ValueError(f"Sequential writer requires an existing isolated run directory: {run_dir}")
    directory = run_dir / settings.output_directory
    if directory.exists():
        raise FileExistsError(f"Sequential artifact directory already exists and will not be overwritten: {directory}")
    directory.mkdir()
    placement_by_id = {value.item_id: value for value in placements}
    attributes = {item.item_id: delivery_attributes_for_item(item) for item in items}
    paths = {
        "plan": directory / settings.plan_document,
        "events": directory / settings.event_log,
        "loading": directory / settings.loading_sequence_table,
        "unloading": directory / settings.unloading_sequence_table,
        "stops": directory / settings.stop_summary_table,
        "metrics": directory / settings.metrics_document,
        "validation": directory / settings.validation_document,
    }
    paths["plan"].write_text(json.dumps(plan.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with paths["events"].open("w", encoding="utf-8", newline="\n") as handle:
        for event in plan.events:
            handle.write(json.dumps(event.to_dict(), sort_keys=True) + "\n")
    _write_sequence(paths["loading"], plan.loading_order, placement_by_id, attributes, sequence_kind="loading")
    _write_sequence(paths["unloading"], plan.unloading_order, placement_by_id, attributes, sequence_kind="unloading")
    _write_rows(paths["stops"], stop_summary_rows(plan))
    paths["metrics"].write_text(json.dumps(simulation_metrics(plan), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    validation = validate_deterministic_plan(plan)
    paths["validation"].write_text(json.dumps({
        "schema_version": "1.0",
        "valid": validation.valid,
        "model": "offline_deterministic_dependency_replay_v1",
        "issues": [
            {"code": issue.code, "message": issue.message, "item_ids": list(issue.item_ids), "container_id": issue.container_id}
            for issue in validation.issues
        ],
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return paths


def validate_sequential_fixture_artifacts(
    run_dir: Path, plan: SimulationPlan, settings: SequentialSimulationSettings
) -> ValidationResult:
    """Compare persisted fixture artifacts with an independently rebuilt plan."""
    directory = run_dir / settings.output_directory
    expected = {
        "plan": directory / settings.plan_document,
        "events": directory / settings.event_log,
        "loading": directory / settings.loading_sequence_table,
        "unloading": directory / settings.unloading_sequence_table,
        "stops": directory / settings.stop_summary_table,
        "metrics": directory / settings.metrics_document,
        "validation": directory / settings.validation_document,
    }
    issues: list[ValidationIssue] = []
    for name, path in expected.items():
        if not path.is_file():
            issues.append(ValidationIssue("SEQUENTIAL_ARTIFACT_MISSING", f"Missing sequential artifact {name}: {path.name}"))
    if issues:
        return ValidationResult(False, issues)
    try:
        if json.loads(expected["plan"].read_text(encoding="utf-8")) != plan.to_dict():
            issues.append(ValidationIssue("SEQUENTIAL_PLAN_ARTIFACT_MISMATCH", "simulation_plan.json differs from the independently rebuilt plan"))
        persisted_events = [json.loads(line) for line in expected["events"].read_text(encoding="utf-8").splitlines() if line]
        if persisted_events != [event.to_dict() for event in plan.events]:
            issues.append(ValidationIssue("SEQUENTIAL_EVENT_ARTIFACT_MISMATCH", "events.jsonl differs from the independently rebuilt plan"))
        _validate_sequence_artifact(expected["loading"], plan.loading_order, "loading", issues)
        _validate_sequence_artifact(expected["unloading"], plan.unloading_order, "unloading", issues)
        if json.loads(expected["metrics"].read_text(encoding="utf-8")) != simulation_metrics(plan):
            issues.append(ValidationIssue("SEQUENTIAL_METRICS_ARTIFACT_MISMATCH", "simulation_metrics.json differs from the independently rebuilt plan"))
        validation = validate_deterministic_plan(plan)
        expected_validation = {
            "schema_version": "1.0", "valid": validation.valid,
            "model": "offline_deterministic_dependency_replay_v1",
            "issues": [
                {"code": issue.code, "message": issue.message, "item_ids": list(issue.item_ids), "container_id": issue.container_id}
                for issue in validation.issues
            ],
        }
        if json.loads(expected["validation"].read_text(encoding="utf-8")) != expected_validation:
            issues.append(ValidationIssue("SEQUENTIAL_VALIDATION_ARTIFACT_MISMATCH", "simulation_validation.json differs from the independently rebuilt plan"))
        _validate_stop_summary_artifact(expected["stops"], stop_summary_rows(plan), issues)
    except (OSError, ValueError, json.JSONDecodeError, csv.Error) as exc:
        issues.append(ValidationIssue("SEQUENTIAL_ARTIFACT_INVALID", f"Cannot read sequential artifact: {exc}"))
    return ValidationResult(not issues, issues)


def _write_sequence(path: Path, order: tuple[str, ...], placements, attributes, *, sequence_kind: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "sequence", "sequence_kind", "item_id", "container_id", "delivery_priority", "delivery_stop_id",
        ])
        writer.writeheader()
        for sequence, item_id in enumerate(order):
            attribute = attributes[item_id]
            writer.writerow({
                "sequence": sequence,
                "sequence_kind": sequence_kind,
                "item_id": item_id,
                "container_id": placements[item_id].container_id,
                "delivery_priority": attribute.delivery_priority,
                "delivery_stop_id": attribute.delivery_stop_id,
            })


def _validate_sequence_artifact(path: Path, order: tuple[str, ...], kind: str, issues: list[ValidationIssue]) -> None:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    observed = [row.get("item_id") for row in rows]
    if observed != list(order):
        issues.append(ValidationIssue(
            "SEQUENTIAL_SEQUENCE_ARTIFACT_MISMATCH",
            f"{path.name} differs from the independently rebuilt {kind} order",
        ))


def _write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames = [
        "delivery_stop_id", "unloaded_item_count", "first_unload_time_seconds",
        "last_unload_end_seconds", "container_ids", "item_ids",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _validate_stop_summary_artifact(path: Path, expected_rows: list[dict[str, object]], issues: list[ValidationIssue]) -> None:
    with path.open(encoding="utf-8", newline="") as handle:
        observed = list(csv.DictReader(handle))
    expected = [{key: str(value) for key, value in row.items()} for row in expected_rows]
    if observed != expected:
        issues.append(ValidationIssue(
            "SEQUENTIAL_STOP_SUMMARY_ARTIFACT_MISMATCH",
            "stop_summary.csv differs from the independently rebuilt plan",
        ))
