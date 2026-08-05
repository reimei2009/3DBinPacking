"""Reusable level orchestration with level-specific model and validation strategies."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from ..algorithms.contracts import AlgorithmOutcome
from ..data_loader import load_config, load_containers, load_items, merge_config
from ..dataset_usage import DatasetExecutionIntent, validate_dataset_usage
from ..instance_data import prepare_instance
from ..reporting import write_run_outputs, write_status_outputs
from ..runtime.project import find_project_root
from ..runtime.run_context import create_run_directory
from ..schemas import Container, Item, Placement, RunResult, SolveResult, ValidationIssue, ValidationResult


@dataclass(frozen=True)
class ValidationBundle:
    result: ValidationResult
    solution_tables: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    validation_documents: dict[str, dict[str, Any]] = field(default_factory=dict)
    solution_payload_extra: dict[str, Any] = field(default_factory=dict)
    scene_item_metadata: dict[str, dict[str, Any]] = field(default_factory=dict)
    extra_report_lines: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    post_write_payload: dict[str, Any] = field(default_factory=dict, repr=False)


Executor = Callable[[str, list[Item], list[Container], dict[str, Any]], AlgorithmOutcome]
InstanceValidator = Callable[[list[Item], list[Container], int], None]
SolutionValidator = Callable[[list[Item], list[Container], list[Placement], dict[str, Any]], ValidationBundle]
ConfigGuard = Callable[[dict[str, Any]], None]
PostWriteHook = Callable[
    [Path, list[Item], list[Container], list[Placement], dict[str, Any], dict[str, Any], ValidationBundle],
    None,
]
PrevalidationMetadataHook = Callable[
    [dict[str, Any], SolveResult, list[Placement], list[Item]],
    dict[str, Any],
]


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
    post_write_hook: PostWriteHook | None = None
    prevalidation_metadata_hook: PrevalidationMetadataHook | None = None


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
    dataset_usage = validate_dataset_usage(
        find_project_root(__file__), config, DatasetExecutionIntent.SOLVER_EXPERIMENT,
    )
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
        "item_count": int(manifest["n_items"]),
        "container_count": int(
            manifest.get("requested_used_container_count", manifest["n_containers"])
        ),
        "container_inventory_count": int(manifest["n_containers"]),
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
            "container_search": config.get("container_search", {}),
        }
    else:
        config.setdefault("algorithms", {}).setdefault(algorithm_id, {}).update(overrides)
        # Level-scoped orchestration budgets are intentionally not solver
        # algorithm parameters.  Preserve them in the strategy settings so a
        # Level 7/8 repair policy can be configured once at the level root.
        runtime_budget_settings = {
            key: value for key, value in config.items()
            if (
                key.startswith("balance_")
                or key.startswith("delivery_")
                or key.startswith("sequential_")
            )
        }
        settings = {
            **config.get("algorithms", {}).get(algorithm_id, {}),
            **runtime_budget_settings,
            "coordinate_tolerance_mm": tolerance, "random_seed": seed,
            "support": config.get("support", {}),
            "stackability": config.get("stackability", {}),
            "load_bearing": config.get("load_bearing", {}),
            "nesting": config.get("nesting", {}),
            "balance": config.get("balance", {}),
            "unloading": config.get("unloading", {}),
            "load_tolerance_kg": config.get("validation", {}).get(
                "load_tolerance_kg", 1e-6
            ),
            "container_search": config.get("container_search", {}),
        }
    started = perf_counter()
    outcome = strategy.execute(algorithm_id, items, containers, settings)
    runtime = perf_counter() - started
    solve, placements = outcome.solve, outcome.placements
    prevalidation_metadata = (
        strategy.prevalidation_metadata_hook(config, solve, placements, items)
        if strategy.prevalidation_metadata_hook is not None
        else {}
    )
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
        "algorithm_role": strategy.algorithm_roles.get(algorithm_id),
        "failure_interpretation": (
            "search_failure_not_mathematical_infeasibility_proof"
            if solve.status == "INFEASIBLE_HEURISTIC" else None
        ),
        "time_limit_seconds": config.get("solver", {}).get("time_limit_seconds") if algorithm_id == "milp_big_m" else None,
        "solver_message": solve.message, "objective_value": solve.objective_value,
        **outcome.metadata,
        # The orchestration timer covers every phase invoked by the strategy.
        # Adapter-local timers remain phase diagnostics and must not overwrite it.
        "algorithm_runtime_seconds": runtime,
        "level": strategy.level_number,
        "items_data_status": "public benchmark sample",
        "cost_note": "Synthetic comparison score; not a real freight price.",
        "item_selection_strategy": manifest["item_selection_strategy"],
        "item_selection_seed": manifest["item_selection_seed"],
        "selected_item_ids_checksum": manifest["selected_item_ids_checksum"],
        "item_profile": manifest["item_profile"],
        "source_adapter": manifest.get("source_adapter"),
        "data_identity": manifest.get("data_identity", {}),
        "data_profile_kind": manifest.get("data_identity", {}).get("profile_kind"),
        "dataset_usage": dataset_usage.to_dict() if dataset_usage is not None else None,
        "dataset_id": manifest.get("data_identity", {}).get("dataset_id"),
        "container_catalog_id": manifest.get("data_identity", {}).get("container_catalog_id"),
        "container_inventory_count": manifest.get("container_inventory_count"),
        "requested_used_container_count": manifest.get(
            "requested_used_container_count"
        ),
        "container_search_enabled": manifest.get("container_search_enabled", False),
        "comparison_group_id": manifest.get("data_identity", {}).get("comparison_group_id"),
        **prevalidation_metadata,
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
            bundle.post_write_payload,
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
        returned_solve = solve
        if (
            outcome.metadata.get("hide_objective_when_invalid")
            or strategy.metadata_defaults.get("hide_objective_when_invalid")
        ):
            metadata["candidate_objective_value"] = metadata.get("objective_value")
            metadata["objective_value"] = None
            metadata["objective_reported"] = False
            returned_solve = SolveResult(
                "INVALID_SOLUTION", "Independent final validation rejected the constructed candidate.",
                None, solve.vector, solve.raw_result,
            )
        if write_outputs and run_dir is not None:
            write_run_outputs(run_dir, placements, containers, metadata, bundle.result, config, **output_arguments)
            if strategy.post_write_hook is not None:
                strategy.post_write_hook(run_dir, items, containers, placements, config, metadata, bundle)
        return RunResult(returned_solve, placements, bundle.result, metadata)
    if write_outputs and run_dir is not None:
        write_run_outputs(run_dir, placements, containers, metadata, bundle.result, config, **output_arguments)
        if strategy.post_write_hook is not None:
            strategy.post_write_hook(run_dir, items, containers, placements, config, metadata, bundle)
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
