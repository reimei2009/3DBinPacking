"""Level-isolated, reproducible output generation."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from .provenance import runtime_metadata, sha256_file
from .runtime.structured_logging import append_event
from .schemas import Container, Placement, ValidationResult
from .visualization.plotly_3d import write_html_views
from .visualization.scene_schema import build_scene

OUTPUT_SCHEMA_VERSION = "1.0"


def write_text(path: str | Path, value: str) -> None:
    """Atomically replace a small text artifact within its destination folder."""
    target = Path(path)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(target)


def write_placements(path: str | Path, placements: list[Placement]) -> None:
    rows = []
    for placement in placements:
        row = asdict(placement)
        row["volume_m3"] = placement.volume_m3
        rows.append(row)
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8")


def container_summary(placements: list[Placement], containers: list[Container]) -> pd.DataFrame:
    rows = []
    for container in containers:
        group = [value for value in placements if value.container_id == container.container_id]
        weight = sum(value.weight_kg for value in group)
        volume = sum(value.volume_m3 for value in group)
        rows.append({
            "container_id": container.container_id, "used": bool(group), "item_count": len(group),
            "loaded_weight_kg": weight, "max_weight_kg": container.max_weight_kg,
            "weight_utilization_pct": 100 * weight / container.max_weight_kg,
            "loaded_volume_m3": volume, "container_volume_m3": container.volume_m3,
            "volume_utilization_pct": 100 * volume / container.volume_m3, "cost": container.cost,
        })
    return pd.DataFrame(rows)


def write_json(path: str | Path, data: dict[str, Any]) -> None:
    write_text(path, json.dumps(data, indent=2, ensure_ascii=False, default=str))


def validation_payload(result: ValidationResult) -> dict[str, Any]:
    return {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "valid": result.valid,
        "issue_count": len(result.issues),
        "issues": [asdict(issue) for issue in result.issues],
    }


def solver_payload(metadata: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "status", "solver", "solver_message", "algorithm_runtime_seconds", "objective_value",
        "n_items", "n_containers", "n_pairs", "n_variables", "n_constraints",
        "constraint_nnz", "big_m", "objective_priority_constant",
        "algorithm_kind", "optimality_proven", "item_ordering", "point_ordering",
        "container_selection_strategy", "candidate_scoring", "subset_enumeration_limit",
        "candidate_subsets_evaluated", "packing_attempts", "extreme_points_evaluated",
        "space_representation", "empty_spaces_evaluated", "empty_spaces_generated",
        "empty_spaces_pruned", "maximum_active_spaces",
        "initial_algorithm", "neighborhoods", "acceptance", "max_iterations", "max_neighbors",
          "subset_candidate_limit", "hill_climbing_iterations", "neighbors_evaluated",
          "repacking_attempts", "accepted_operators", "initial_score", "final_score", "improved",
          "neighbors_per_iteration", "initial_temperature", "cooling_rate", "minimum_temperature",
          "final_temperature", "annealing_iterations", "accepted_moves", "accepted_worse_moves",
          "best_improvements", "accepted_operator_counts", "final_current_score", "best_score",
          "allow_worse_subsets",
          "algorithm_parameters",
      )
    return {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        **{key: metadata[key] for key in keys if metadata.get(key) is not None},
    }


def metrics_payload(metadata: dict[str, Any], validation_valid: bool | None) -> dict[str, Any]:
    return {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "level": metadata["level_id"],
        "algorithm": metadata["algorithm_id"],
        "status": metadata["status"],
        "objective_value": metadata.get("objective_value"),
        "container_count": metadata.get("container_count"),
        "total_container_cost": metadata.get("total_container_cost"),
        "n_items": metadata["n_items"],
        "n_containers_available": metadata["n_containers"],
        "algorithm_runtime_seconds": metadata.get("algorithm_runtime_seconds"),
        "validation_valid": validation_valid,
    }


def _initialize_run(
    run_dir: Path, metadata: dict[str, Any], config: dict[str, Any],
    items_path: Path, containers_path: Path, project_root: Path,
) -> dict[str, Any]:
    directories = ["input_snapshot", "logs", "solver", "solution", "validation", "metrics", "reports", "visualization"]
    for name in directories:
        (run_dir / name).mkdir(parents=True, exist_ok=True)
    shutil.copy2(items_path, run_dir / "input_snapshot" / "items.csv")
    shutil.copy2(containers_path, run_dir / "input_snapshot" / "containers.csv")
    resolved_config_path = run_dir / "resolved_config.yaml"
    write_text(resolved_config_path, yaml.safe_dump(config, sort_keys=False))
    manifest = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "project": "3d-container-packing",
        "level": metadata["level_id"], "run_id": metadata["run_id"],
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "algorithm": metadata["algorithm_id"], "solver": metadata["solver"],
        "environment": metadata["environment"], "dataset_name": metadata["instance_id"],
        "dataset_files": ["input_snapshot/items.csv", "input_snapshot/containers.csv"],
        "dataset_checksums": {
            "items": sha256_file(items_path), "containers": sha256_file(containers_path),
        },
        "config_file": metadata.get("config_file"),
        "resolved_config_checksum": sha256_file(resolved_config_path),
        "random_seed": metadata["random_seed"],
        "time_limit_seconds": metadata.get("time_limit_seconds"),
        "active_constraints": ["exact_assignment", "container_activation", "boundaries", "payload", "pairwise_non_overlap"],
        "inactive_constraints": ["rotation", "stackability", "support", "stability", "fragility", "center_of_gravity"],
        "status": metadata["status"],
        "validation_status": "NOT_RUN",
        "artifacts": {
            "canonical": [
                "manifest.json", "resolved_config.yaml", "input_snapshot/items.csv",
                "input_snapshot/containers.csv",
            ],
            "exports": ["metrics/metrics.json"],
            "derived": [],
            "diagnostics": ["logs/run.log", "solver/solver_summary.json", "solver/raw_solver_output.txt"],
        },
        **runtime_metadata(project_root),
    }
    write_json(run_dir / "manifest.json", manifest)
    return manifest


def write_status_outputs(
    run_dir: Path, metadata: dict[str, Any], config: dict[str, Any], *,
    items_path: Path, containers_path: Path, project_root: Path,
    validation: ValidationResult | None = None,
) -> None:
    manifest = _initialize_run(run_dir, metadata, config, items_path, containers_path, project_root)
    write_json(run_dir / "solver" / "solver_summary.json", solver_payload(metadata))
    write_text(run_dir / "solver" / "raw_solver_output.txt", metadata.get("solver_message", "") + "\n")
    write_json(run_dir / "metrics" / "metrics.json", metrics_payload(metadata, None if validation is None else validation.valid))
    validation_status = "NOT_RUN"
    if validation is not None:
        validation_status = "VALID" if validation.valid else "INVALID"
        write_json(run_dir / "validation" / "validation_report.json", validation_payload(validation))
        pd.DataFrame(
            [asdict(value) for value in validation.issues],
            columns=["code", "message", "item_ids", "container_id"],
        ).to_csv(run_dir / "validation" / "violations.csv", index=False)
        manifest["validation_status"] = validation_status
        manifest["artifacts"]["canonical"].append("validation/validation_report.json")
        manifest["artifacts"]["exports"].append("validation/violations.csv")
    append_event(
        run_dir / "logs" / "run.log", "experiment_completed",
        run_id=metadata["run_id"], level=metadata["level_id"], algorithm=metadata["algorithm_id"],
        status=metadata["status"], validation_status=validation_status,
    )
    write_json(run_dir / "manifest.json", manifest)


def write_run_outputs(
    run_dir: Path, placements: list[Placement], containers: list[Container],
    metadata: dict[str, Any], validation: ValidationResult, config: dict[str, Any], *,
    items_path: Path, containers_path: Path, project_root: Path,
) -> None:
    manifest = _initialize_run(run_dir, metadata, config, items_path, containers_path, project_root)
    manifest["artifacts"]["canonical"].extend(["solution/solution.json", "validation/validation_report.json"])
    manifest["artifacts"]["exports"].extend([
        "solution/placements.csv", "solution/containers.csv", "validation/violations.csv",
    ])
    manifest["artifacts"]["derived"].extend([
        "reports/summary.md", "visualization/scene.json", "visualization/combined_scene.html",
    ])
    summary = container_summary(placements, containers)
    validation_data = validation_payload(validation)
    write_placements(run_dir / "solution" / "placements.csv", placements)
    summary.to_csv(run_dir / "solution" / "containers.csv", index=False)
    write_json(run_dir / "solution" / "solution.json", {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "level": metadata["level_id"],
        "placements": [asdict(value) for value in placements],
    })
    write_json(run_dir / "solver" / "solver_summary.json", solver_payload(metadata))
    write_text(run_dir / "solver" / "raw_solver_output.txt", metadata.get("solver_message", "") + "\n")
    write_json(run_dir / "validation" / "validation_report.json", validation_data)
    pd.DataFrame([asdict(value) for value in validation.issues], columns=["code", "message", "item_ids", "container_id"]).to_csv(
        run_dir / "validation" / "violations.csv", index=False
    )
    write_json(run_dir / "metrics" / "metrics.json", metrics_payload(metadata, validation.valid))
    scene = build_scene(
        placements,
        containers,
        level_id=metadata["level_id"],
        algorithm_id=metadata["algorithm_id"],
        validation_status="VALID" if validation.valid else "INVALID",
    )
    write_json(run_dir / "visualization" / "scene.json", scene)
    html_views = write_html_views(scene, run_dir / "visualization")
    manifest["artifacts"]["derived"].extend(
        path.relative_to(run_dir).as_posix() for path in html_views[1:]
    )
    append_event(
        run_dir / "logs" / "run.log", "experiment_completed",
        run_id=metadata["run_id"], level=metadata["level_id"], algorithm=metadata["algorithm_id"],
        status=metadata["status"], objective_value=metadata.get("objective_value"),
        validation_status="VALID" if validation.valid else "INVALID",
    )
    write_text(run_dir / "reports" / "summary.md",
        f"# Run {metadata['run_id']}\n\n- Status: {metadata['status']}\n- Objective: {metadata.get('objective_value')}\n"
        f"- Selected containers: {metadata.get('selected_containers', [])}\n- Validation: {validation.valid}\n"
    )
    manifest["validation_status"] = "VALID" if validation.valid else "INVALID"
    write_json(run_dir / "manifest.json", manifest)
