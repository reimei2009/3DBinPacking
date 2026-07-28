"""Isolated Level 8 fixture evidence writer; no Level 8 runtime is registered."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any

import pandas as pd

from ..reporting import write_run_outputs
from ..schemas import Container, Item, Placement
from .level_08_validation import Level08UnloadingValidation
from .pipeline import ValidationBundle


def write_level_08_fixture_validation_run(
    run_dir: Path,
    items: list[Item],
    containers: list[Container],
    placements: list[Placement],
    validation: Level08UnloadingValidation,
    config: dict[str, Any],
    *,
    items_path: Path,
    containers_path: Path,
    project_root: Path,
    run_id: str,
    fixture_id: str,
    random_seed: int = 42,
) -> dict[str, Any]:
    """Persist static LIFO evidence in an isolated, non-overwritable run."""
    _assert_isolated_run_dir(run_dir)
    run_dir.mkdir(parents=True, exist_ok=False)
    used = sorted({placement.container_id for placement in placements})
    metadata = {
        "level_id": "level_08",
        "run_id": run_id,
        "algorithm_id": "level_08_fixture_validation_bundle",
        "algorithm_role": "unregistered_fixture_validation_only",
        "solver": "not_applicable_validation_only",
        "solver_message": "Level 8 static unload/LIFO fixture validation; no solver was invoked.",
        "status": "VALIDATION_ONLY" if validation.result.valid else "INVALID_SOLUTION",
        "objective_value": None,
        "environment": "local",
        "instance_id": fixture_id,
        "random_seed": random_seed,
        "n_items": len(items),
        "n_containers": len(containers),
        "container_count": len(used),
        "selected_containers": used,
        "validation_valid": validation.result.valid,
        "unloading_model": "straight_path_static_lifo_v1",
        "door_face": validation.settings.door_face if validation.settings else None,
        "delivery_priority_direction": validation.settings.delivery_priority_direction if validation.settings else None,
        "rehandle_count_mode": validation.settings.rehandle_count_mode if validation.settings else None,
        "total_direct_rehandles": sum(record.minimum_rehandle_count for record in validation.records),
        "lifo_compliant_item_count": sum(record.lifo_compliant for record in validation.records),
        "lifo_noncompliant_item_count": sum(not record.lifo_compliant for record in validation.records),
        "active_constraints": ["explicit_delivery_metadata", "static_straight_path_accessibility", "lifo_later_priority_blockers"],
        "inactive_constraints": ["level_08_solver", "exact_removal_sequence", "handling_equipment", "temporary_staging_space"],
    }
    write_run_outputs(
        run_dir, placements, containers, metadata, validation.result, config,
        items_path=items_path, containers_path=containers_path, project_root=project_root,
        extra_solution_tables={
            "unloading_accessibility.csv": validation.accessibility_rows(),
            "rehandle_plan.csv": validation.rehandle_rows(),
        },
        extra_validation_documents={"unloading_validation.json": validation.payload()},
        solution_payload_extra={"unloading": validation.payload()},
        extra_report_lines=[
            f"- Level 8 LIFO static validation: {'VALID' if validation.result.valid else 'INVALID'}.",
            f"- Direct later-priority rehandles: {metadata['total_direct_rehandles']}",
        ],
    )
    # A valid LIFO fixture has no rehandle rows, but the artifact must retain a
    # stable inspectable schema rather than becoming an empty, headerless CSV.
    if not validation.rehandle_rows():
        pd.DataFrame(columns=[
            "target_item_id", "container_id", "target_delivery_priority", "blocker_item_id",
            "blocker_relation", "rehandle_rank", "counting_model",
        ]).to_csv(run_dir / "solution" / "rehandle_plan.csv", index=False, encoding="utf-8")
    return metadata


def write_level_08_composed_validation_run(
    run_dir: Path,
    items: list[Item],
    containers: list[Container],
    placements: list[Placement],
    inherited: ValidationBundle,
    unloading: Level08UnloadingValidation,
    config: dict[str, Any],
    *,
    items_path: Path,
    containers_path: Path,
    project_root: Path,
    run_id: str,
    instance_id: str,
    random_seed: int,
    runtime_seconds: float,
    algorithm_id: str = "level_08_fixture_validation_bundle",
    algorithm_role: str = "cli_only_composed_validation_fixture",
    solver: str = "not_applicable_validation_only",
    solver_message: str = "Level 8 composed inherited and unload/LIFO fixture validation; no packing solver was invoked.",
    status: str | None = None,
    objective_value: float | None = None,
    metadata_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write one Level 8 run containing inherited and unloading evidence."""
    _assert_isolated_run_dir(run_dir)
    run_dir.mkdir(parents=True, exist_ok=False)
    selected = sorted({placement.container_id for placement in placements})
    total_cost = sum(value.cost for value in containers if value.container_id in selected)
    metadata = {
        "level_id": "level_08",
        "run_id": run_id,
        "algorithm_id": algorithm_id,
        "algorithm_role": algorithm_role,
        "solver": solver,
        "solver_message": solver_message,
        "status": status or ("VALIDATION_ONLY" if inherited.result.valid and unloading.result.valid else "INVALID_SOLUTION"),
        "objective_value": objective_value,
        "environment": "local",
        "instance_id": instance_id,
        "random_seed": random_seed,
        "n_items": len(items),
        "n_containers": len(containers),
        "container_count": len(selected),
        "total_container_cost": total_cost,
        "selected_containers": selected,
        "input_fingerprint": _input_fingerprint(items_path, containers_path),
        "algorithm_runtime_seconds": runtime_seconds,
        "unloading_model": "straight_path_static_lifo_v1",
        "door_face": unloading.settings.door_face if unloading.settings else None,
        "delivery_priority_direction": unloading.settings.delivery_priority_direction if unloading.settings else None,
        "rehandle_count_mode": unloading.settings.rehandle_count_mode if unloading.settings else None,
        "total_direct_rehandles": sum(record.minimum_rehandle_count for record in unloading.records),
        "lifo_compliant_item_count": sum(record.lifo_compliant for record in unloading.records),
        "lifo_noncompliant_item_count": sum(not record.lifo_compliant for record in unloading.records),
        "level_08_runtime_status": "cli_only_validation_fixture" if algorithm_id == "level_08_fixture_validation_bundle" else "cli_only_constructive_ab_fixture",
        "active_constraints": [
            "inherited_level_01_to_level_07_validation",
            "explicit_delivery_metadata", "static_straight_path_accessibility",
            "lifo_later_priority_blockers",
        ],
        "inactive_constraints": [
            "exact_removal_sequence", "handling_equipment", "temporary_staging_space",
        ],
        **inherited.metadata,
        **(metadata_extra or {}),
    }
    documents = {
        **inherited.validation_documents,
        "unloading_validation.json": unloading.payload(),
    }
    tables = {
        **inherited.solution_tables,
        "unloading_accessibility.csv": unloading.accessibility_rows(),
        "rehandle_plan.csv": unloading.rehandle_rows(),
    }
    from ..schemas import ValidationResult

    issues = [*inherited.result.issues, *unloading.result.issues]
    combined = ValidationResult(not issues, issues)
    write_run_outputs(
        run_dir, placements, containers, metadata, combined, config,
        items_path=items_path, containers_path=containers_path, project_root=project_root,
        extra_solution_tables=tables,
        extra_validation_documents=documents,
        solution_payload_extra={
            **inherited.solution_payload_extra,
            "unloading": unloading.payload(),
        },
        scene_item_metadata=inherited.scene_item_metadata,
        extra_report_lines=[
            *inherited.extra_report_lines,
            f"- Level 8 static LIFO validation: {'VALID' if unloading.result.valid else 'INVALID'}.",
            f"- Direct later-priority rehandles: {metadata['total_direct_rehandles']}",
        ],
    )
    _ensure_empty_rehandle_schema(run_dir, unloading)
    return metadata


def _assert_isolated_run_dir(run_dir: Path) -> None:
    if run_dir.parent.name != "runs" or run_dir.parent.parent.name != "level_08":
        raise ValueError("Level 8 fixture output must be under outputs/level_08/runs/<run_id>")
    if run_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing Level 8 fixture run: {run_dir}")


def _ensure_empty_rehandle_schema(run_dir: Path, validation: Level08UnloadingValidation) -> None:
    if validation.rehandle_rows():
        return
    pd.DataFrame(columns=[
        "target_item_id", "container_id", "target_delivery_priority", "blocker_item_id",
        "blocker_relation", "rehandle_rank", "counting_model",
    ]).to_csv(run_dir / "solution" / "rehandle_plan.csv", index=False, encoding="utf-8")


def _input_fingerprint(items_path: Path, containers_path: Path) -> str:
    """Stable identity for comparing A/B runs that share the same input snapshot."""
    digest = sha256()
    for path in (items_path, containers_path):
        digest.update(path.read_bytes())
    return digest.hexdigest()
