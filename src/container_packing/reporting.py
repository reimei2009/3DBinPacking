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
        "algorithm_kind", "algorithm_role", "failure_interpretation", "optimality_proven",
        "item_ordering", "point_ordering",
        "mip_gap", "mip_dual_bound", "mip_node_count",
        "feasibility_policy", "candidate_feasibility_checks", "geometry_rejected_candidates",
        "orientation_provider", "orientation_profile", "orientation_candidates_evaluated",
        "heuristic_support_threshold", "heuristic_support_epsilon_mm",
        "support_rejected_candidates", "support_valid_candidates",
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
          "support_grid_x", "support_grid_y", "support_grid_size", "support_threshold",
          "minimum_supported_points", "floor_variable_count", "support_point_variable_count",
          "center_support_variable_count",
          "capacity_strengthening_enabled", "capacity_strengthening_cut_count",
          "container_count_lower_bound", "volume_container_count_lower_bound",
          "payload_container_count_lower_bound",
          "model_support_audit_valid", "model_support_audit_issue_count", "model_support_audit_examples",
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
        "algorithm_role": metadata.get("algorithm_role"),
        "status": metadata["status"],
        "objective_value": metadata.get("objective_value"),
        "container_count": metadata.get("container_count"),
        "total_container_cost": metadata.get("total_container_cost"),
        "n_items": metadata["n_items"],
        "n_containers_available": metadata["n_containers"],
        "algorithm_runtime_seconds": metadata.get("algorithm_runtime_seconds"),
        "mip_gap": metadata.get("mip_gap"),
        "mip_dual_bound": metadata.get("mip_dual_bound"),
        "mip_node_count": metadata.get("mip_node_count"),
        "feasibility_policy": metadata.get("feasibility_policy"),
        "support_rejected_candidates": metadata.get("support_rejected_candidates"),
        "support_valid_candidates": metadata.get("support_valid_candidates"),
        "validation_valid": validation_valid,
        "item_selection_strategy": metadata.get("item_selection_strategy"),
        "item_selection_seed": metadata.get("item_selection_seed"),
        "selected_item_ids_checksum": metadata.get("selected_item_ids_checksum"),
        "support_enabled": metadata.get("support_enabled", False),
        "support_threshold": metadata.get("support_threshold"),
        "minimum_exact_support_ratio": metadata.get("minimum_exact_support_ratio"),
        "all_centers_supported": metadata.get("all_centers_supported"),
        "orientation_profile": metadata.get("orientation_profile"),
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
        "algorithm_role": metadata.get("algorithm_role"),
        "environment": metadata["environment"], "dataset_name": metadata["instance_id"],
        "dataset_files": ["input_snapshot/items.csv", "input_snapshot/containers.csv"],
        "dataset_checksums": {
            "items": sha256_file(items_path), "containers": sha256_file(containers_path),
        },
        "item_selection": {
            "strategy": metadata.get("item_selection_strategy"),
            "seed": metadata.get("item_selection_seed"),
            "selected_item_ids_checksum": metadata.get("selected_item_ids_checksum"),
            "profile": metadata.get("item_profile"),
        },
        "config_file": metadata.get("config_file"),
        "resolved_config_checksum": sha256_file(resolved_config_path),
        "config_overrides": metadata.get("config_overrides", {}),
        "support_threshold": metadata.get("support_threshold"),
        "orientation_profile": metadata.get("orientation_profile"),
        "orientation_data_status": metadata.get("orientation_data_status"),
        "random_seed": metadata["random_seed"],
        "time_limit_seconds": metadata.get("time_limit_seconds"),
        "active_constraints": metadata.get("active_constraints", [
            "exact_assignment", "container_activation", "boundaries", "payload", "pairwise_non_overlap",
        ]),
        "inactive_constraints": metadata.get("inactive_constraints", [
            "rotation", "stackability", "support", "stability", "fragility", "center_of_gravity",
        ]),
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
    extra_solution_tables: dict[str, list[dict[str, Any]]] | None = None,
    extra_validation_documents: dict[str, dict[str, Any]] | None = None,
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
    _write_extra_artifacts(run_dir, manifest, extra_solution_tables, extra_validation_documents)
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
    extra_solution_tables: dict[str, list[dict[str, Any]]] | None = None,
    extra_validation_documents: dict[str, dict[str, Any]] | None = None,
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
    _write_extra_artifacts(run_dir, manifest, extra_solution_tables, extra_validation_documents)
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
        f"- Algorithm role: {metadata.get('algorithm_role')}\n"
        f"- Selected containers: {metadata.get('selected_containers', [])}\n- Validation: {validation.valid}\n"
    )
    manifest["validation_status"] = "VALID" if validation.valid else "INVALID"
    write_json(run_dir / "manifest.json", manifest)


def _write_extra_artifacts(
    run_dir: Path,
    manifest: dict[str, Any],
    solution_tables: dict[str, list[dict[str, Any]]] | None,
    validation_documents: dict[str, dict[str, Any]] | None,
) -> None:
    """Persist level-specific artifacts without changing canonical placement schemas."""
    for filename, rows in (solution_tables or {}).items():
        if Path(filename).name != filename or not filename.endswith(".csv"):
            raise ValueError(f"Invalid additional solution filename: {filename}")
        pd.DataFrame(rows).to_csv(run_dir / "solution" / filename, index=False, encoding="utf-8")
        manifest["artifacts"]["exports"].append(f"solution/{filename}")
    for filename, payload in (validation_documents or {}).items():
        if Path(filename).name != filename or not filename.endswith(".json"):
            raise ValueError(f"Invalid additional validation filename: {filename}")
        write_json(run_dir / "validation" / filename, payload)
        manifest["artifacts"]["canonical"].append(f"validation/{filename}")
