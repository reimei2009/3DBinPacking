"""Reusable level orchestration with level-specific model and validation strategies."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from ..algorithms.contracts import AlgorithmOutcome
from ..data_loader import load_config, load_containers, load_items, merge_config
from ..instance_data import prepare_instance
from ..reporting import write_run_outputs, write_status_outputs
from ..runtime.project import find_project_root
from ..runtime.run_context import create_run_directory
from ..schemas import Container, Item, Placement, RunResult, ValidationIssue, ValidationResult


@dataclass(frozen=True)
class ValidationBundle:
    result: ValidationResult
    solution_tables: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    validation_documents: dict[str, dict[str, Any]] = field(default_factory=dict)
    solution_payload_extra: dict[str, Any] = field(default_factory=dict)
    scene_item_metadata: dict[str, dict[str, Any]] = field(default_factory=dict)
    extra_report_lines: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


Executor = Callable[[str, list[Item], list[Container], dict[str, Any]], AlgorithmOutcome]
InstanceValidator = Callable[[list[Item], list[Container], int], None]
SolutionValidator = Callable[[list[Item], list[Container], list[Placement], dict[str, Any]], ValidationBundle]
ConfigGuard = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class LevelRuntimeStrategy:
    level_number: int
    execute: Executor
    validate_instance: InstanceValidator
    validate_solution: SolutionValidator
    guard_config: ConfigGuard
    active_constraints: tuple[str, ...]
    inactive_constraints: tuple[str, ...]
    metadata_defaults: dict[str, Any]
    algorithm_roles: dict[str, str] = field(default_factory=dict)


def run_configured_level(
    config_path: str | Path,
    *,
    strategy: LevelRuntimeStrategy,
    item_count: int | None = None,
    container_count: int | None = None,
    write_outputs: bool = True,
    level_id: str,
    algorithm_id: str,
    environment: str = "local",
    random_seed: int | None = None,
    algorithm_parameters: dict[str, Any] | None = None,
    config_overrides: dict[str, Any] | None = None,
    item_selection_strategy: str | None = None,
    item_selection_seed: int | None = None,
) -> RunResult:
    config_file = Path(config_path).resolve()
    config = load_config(config_file)
    config = merge_config(config, dict(config_overrides or {}))
    seed = int(config.get("project", {}).get("random_seed", 42) if random_seed is None else random_seed)
    if seed < 0:
        raise ValueError(f"random_seed must be zero or greater, got {seed}")
    config.setdefault("project", {})["random_seed"] = seed
    strategy.guard_config(config)
    root = find_project_root(__file__)
    paths = config["paths"]
    manifest = prepare_instance(
        root, config, item_count=item_count, container_count=container_count, level_id=level_id,
        item_selection_strategy=item_selection_strategy, item_selection_seed=item_selection_seed,
    )
    config.setdefault("instance", {}).update({
        "item_count": int(manifest["n_items"]), "container_count": int(manifest["n_containers"]),
        "item_selection_strategy": manifest["item_selection_strategy"],
        "item_selection_seed": manifest["item_selection_seed"],
        "selected_item_ids_checksum": manifest["selected_item_ids_checksum"],
    })
    items_path = _resolve_path(root, manifest["items_csv"])
    containers_path = _resolve_path(root, manifest["containers_csv"])
    items, containers = load_items(items_path), load_containers(containers_path)
    strategy.validate_instance(items, containers, int(manifest["n_items"]))
    tolerance = float(config.get("validation", {}).get("coordinate_tolerance_mm", 1e-4))
    overrides = dict(algorithm_parameters or {})
    if algorithm_id == "milp_big_m":
        config.setdefault("solver", {}).update(overrides)
        settings = {
            **config.get("solver", {}), "coordinate_tolerance_mm": tolerance,
            "support": config.get("support", {}),
        }
    else:
        config.setdefault("algorithms", {}).setdefault(algorithm_id, {}).update(overrides)
        settings = {
            **config.get("algorithms", {}).get(algorithm_id, {}),
            "coordinate_tolerance_mm": tolerance, "random_seed": seed,
            "support": config.get("support", {}),
            "stackability": config.get("stackability", {}),
            "load_bearing": config.get("load_bearing", {}),
            "load_tolerance_kg": config.get("validation", {}).get(
                "load_tolerance_kg", 1e-6
            ),
        }
    started = perf_counter()
    outcome = strategy.execute(algorithm_id, items, containers, settings)
    runtime = perf_counter() - started
    solve, placements = outcome.solve, outcome.placements
    run_id: str | None = None
    run_dir: Path | None = None
    if write_outputs:
        output_root = _resolve_path(root, paths.get("output_root", "outputs"))
        run_id, run_dir = create_run_directory(output_root, level_id, algorithm_id, len(items), len(containers), seed)
    metadata: dict[str, Any] = {
        "status": solve.status, "solver": outcome.backend, "instance_id": manifest["instance_id"],
        "run_id": run_id, "run_dir": _display_path(root, run_dir), "level_id": level_id,
        "algorithm_id": algorithm_id, "environment": environment,
        "config_file": _display_path(root, config_file), "random_seed": seed,
        "algorithm_parameters": overrides, "config_overrides": dict(config_overrides or {}),
        "algorithm_runtime_seconds": runtime,
        "algorithm_role": strategy.algorithm_roles.get(algorithm_id),
        "failure_interpretation": (
            "search_failure_not_mathematical_infeasibility_proof"
            if solve.status == "INFEASIBLE_HEURISTIC" else None
        ),
        "time_limit_seconds": config.get("solver", {}).get("time_limit_seconds") if algorithm_id == "milp_big_m" else None,
        "solver_message": solve.message, "objective_value": solve.objective_value,
        **outcome.metadata, "level": strategy.level_number,
        "items_data_status": "public benchmark sample",
        "cost_note": "Synthetic comparison score; not a real freight price.",
        "item_selection_strategy": manifest["item_selection_strategy"],
        "item_selection_seed": manifest["item_selection_seed"],
        "selected_item_ids_checksum": manifest["selected_item_ids_checksum"],
        "item_profile": manifest["item_profile"],
        "active_constraints": list(strategy.active_constraints),
        "inactive_constraints": list(strategy.inactive_constraints),
        **strategy.metadata_defaults,
    }
    if solve.status not in {"OPTIMAL", "FEASIBLE", "FEASIBLE_TIME_LIMIT"} or len(placements) != len(items):
        if write_outputs and run_dir is not None:
            write_status_outputs(run_dir, metadata, config, items_path=items_path, containers_path=containers_path, project_root=root)
        return RunResult(solve, [], None, metadata)

    bundle = strategy.validate_solution(items, containers, placements, config)
    if outcome.metadata.get("model_support_audit_valid") is False:
        audit_issue = ValidationIssue(
            "MODEL_SUPPORT_MISMATCH",
            f"{outcome.metadata.get('model_support_audit_issue_count', 0)} active support decisions do not match decoded geometry",
        )
        documents = {name: dict(payload) for name, payload in bundle.validation_documents.items()}
        if "support_validation.json" in documents:
            documents["support_validation.json"].update({
                "valid": False,
                "model_support_audit_valid": False,
                "model_support_audit_issue_count": outcome.metadata.get("model_support_audit_issue_count", 0),
            })
        bundle = ValidationBundle(
            ValidationResult(False, [*bundle.result.issues, audit_issue]),
            bundle.solution_tables, documents, bundle.solution_payload_extra,
            bundle.scene_item_metadata, bundle.extra_report_lines, bundle.metadata,
        )
    selected = sorted({placement.container_id for placement in placements})
    container_map = {container.container_id: container for container in containers}
    metadata.update({
        "container_count": len(selected), "selected_containers": selected,
        "total_container_cost": sum(container_map[value].cost for value in selected),
        "validation_valid": bundle.result.valid,
        **bundle.metadata,
    })
    output_arguments = {
        "items_path": items_path, "containers_path": containers_path, "project_root": root,
        "extra_solution_tables": bundle.solution_tables,
        "extra_validation_documents": bundle.validation_documents,
        "solution_payload_extra": bundle.solution_payload_extra,
        "scene_item_metadata": bundle.scene_item_metadata,
        "extra_report_lines": bundle.extra_report_lines,
    }
    if not bundle.result.valid:
        metadata["status"] = "INVALID_SOLUTION"
        if write_outputs and run_dir is not None:
            write_status_outputs(run_dir, metadata, config, validation=bundle.result, **output_arguments)
        return RunResult(solve, placements, bundle.result, metadata)
    if write_outputs and run_dir is not None:
        write_run_outputs(run_dir, placements, containers, metadata, bundle.result, config, **output_arguments)
    return RunResult(solve, placements, bundle.result, metadata)


def _resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _display_path(root: Path, value: Path | None) -> str | None:
    if value is None:
        return None
    try:
        return value.relative_to(root).as_posix()
    except ValueError:
        return str(value.resolve())
