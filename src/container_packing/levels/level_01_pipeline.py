"""End-to-end Level 1 solve and validation orchestration."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any

from ..data_loader import load_config, load_containers, load_items
from ..instance_data import prepare_instance
from ..reporting import write_run_outputs, write_status_outputs
from ..runtime.run_context import create_run_directory
from ..runtime.project import find_project_root
from ..schemas import RunResult
from .level_01_algorithms import execute_level_01
from .level_01_preprocessing import validate_instance
from .level_01_validation import validate_solution


def project_root() -> Path:
    return find_project_root(__file__)


def resolve_path(root: Path, value: str | Path) -> Path:
    candidate = Path(value)
    return candidate if candidate.is_absolute() else root / candidate


def display_path(root: Path, value: Path | None) -> str | None:
    if value is None:
        return None
    try:
        return value.relative_to(root).as_posix()
    except ValueError:
        return str(value.resolve())


def run_from_config(
    config_path: str | Path,
    *,
    item_count: int | None = None,
    container_count: int | None = None,
    write_outputs: bool = True,
    level_id: str = "level_01",
    algorithm_id: str = "milp_big_m",
    environment: str = "local",
    random_seed: int | None = None,
    algorithm_parameters: dict[str, Any] | None = None,
) -> RunResult:
    """Prepare, solve, validate, and report one dynamically sized instance."""
    config_file = Path(config_path).resolve()
    config = load_config(config_file)
    seed = int(config.get("project", {}).get("random_seed", 42) if random_seed is None else random_seed)
    if seed < 0:
        raise ValueError(f"random_seed must be zero or greater, got {seed}")
    config.setdefault("project", {})["random_seed"] = seed
    root = project_root()
    paths = config["paths"]
    manifest = prepare_instance(
        root, config, item_count=item_count, container_count=container_count, level_id=level_id
    )
    items_path = resolve_path(root, manifest["items_csv"])
    containers_path = resolve_path(root, manifest["containers_csv"])
    items = load_items(items_path)
    containers = load_containers(containers_path)
    validate_instance(items, containers, expected_items=int(manifest["n_items"]))
    model_settings = config.get("model", {})
    forbidden = {
        "allow_rotation": model_settings.get("allow_rotation", False),
        "enforce_stability": model_settings.get("enforce_stability", False),
        "enforce_stackability": model_settings.get("enforce_stackability", False),
    }
    enabled = [name for name, value in forbidden.items() if value]
    if enabled:
        raise ValueError(f"Level 1 does not support enabled options: {', '.join(enabled)}")
    tolerance = float(config.get("validation", {}).get("coordinate_tolerance_mm", 1e-4))
    weight_tolerance = float(config.get("validation", {}).get("weight_tolerance_kg", 1e-6))
    overrides = dict(algorithm_parameters or {})
    if algorithm_id == "milp_big_m":
        config.setdefault("solver", {}).update(overrides)
        algorithm_settings = {**config.get("solver", {}), "coordinate_tolerance_mm": tolerance}
    else:
        config.setdefault("algorithms", {}).setdefault(algorithm_id, {}).update(overrides)
        algorithm_settings = {
            **config.get("algorithms", {}).get(algorithm_id, {}),
            "coordinate_tolerance_mm": tolerance, "random_seed": seed,
        }
    algorithm_started = perf_counter()
    outcome = execute_level_01(algorithm_id, items, containers, algorithm_settings)
    algorithm_runtime_seconds = perf_counter() - algorithm_started
    solve = outcome.solve
    placements = outcome.placements
    run_id: str | None = None
    run_dir: Path | None = None
    if write_outputs:
        output_root = resolve_path(root, paths.get("output_root", "outputs"))
        run_id, run_dir = create_run_directory(
            output_root, level_id, algorithm_id, len(items), len(containers), seed
        )
    base_metadata: dict[str, Any] = {
        "status": solve.status, "solver": outcome.backend,
        "instance_id": manifest["instance_id"],
        "run_id": run_id, "run_dir": display_path(root, run_dir),
        "level_id": level_id, "algorithm_id": algorithm_id, "environment": environment,
        "config_file": display_path(root, config_file),
        "random_seed": seed,
        "algorithm_parameters": overrides,
        "algorithm_runtime_seconds": algorithm_runtime_seconds,
        "time_limit_seconds": config.get("solver", {}).get("time_limit_seconds") if algorithm_id == "milp_big_m" else None,
        "solver_message": solve.message, "objective_value": solve.objective_value,
        **outcome.metadata, "level": 1, "rotation_enabled": False,
        "stability_enabled": False, "stackability_enabled": False,
        "items_data_status": "public benchmark sample",
        "containers_data_status": "synthetic_level1",
        "cost_note": "Synthetic comparison score; not a real freight price.",
    }
    if solve.status not in {"OPTIMAL", "FEASIBLE", "FEASIBLE_TIME_LIMIT"} or len(placements) != len(items):
        if write_outputs and run_dir is not None:
            write_status_outputs(
                run_dir, base_metadata, config, items_path=items_path,
                containers_path=containers_path, project_root=root,
            )
        return RunResult(solve=solve, placements=[], validation=None, metadata=base_metadata)
    validation = validate_solution(items, containers, placements, coordinate_tolerance=tolerance, weight_tolerance=weight_tolerance)
    selected = sorted({placement.container_id for placement in placements})
    container_map = {container.container_id: container for container in containers}
    metadata = {
        **base_metadata, "container_count": len(selected), "selected_containers": selected,
        "total_container_cost": sum(container_map[c].cost for c in selected),
        "validation_valid": validation.valid,
    }
    if not validation.valid:
        metadata["status"] = "INVALID_SOLUTION"
        if write_outputs and run_dir is not None:
            write_status_outputs(
                run_dir, metadata, config, items_path=items_path,
                containers_path=containers_path, project_root=root, validation=validation,
            )
        return RunResult(solve=solve, placements=placements, validation=validation, metadata=metadata)
    if write_outputs and run_dir is not None:
        write_run_outputs(
            run_dir, placements, containers, metadata, validation, config,
            items_path=items_path, containers_path=containers_path, project_root=root,
        )
    return RunResult(solve=solve, placements=placements, validation=validation, metadata=metadata)
