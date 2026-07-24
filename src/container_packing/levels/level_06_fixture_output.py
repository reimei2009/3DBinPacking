"""Isolated output writer for the non-registered Level 6 FFD fixture adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..reporting import write_run_outputs, write_status_outputs
from ..schemas import Container
from .level_06_ffd_adapter import Level06NestingFfdFixtureResult


def write_nesting_aware_ffd_fixture_run(
    run_dir: Path,
    result: Level06NestingFfdFixtureResult,
    containers: list[Container],
    config: dict[str, Any],
    *,
    items_path: Path,
    containers_path: Path,
    project_root: Path,
    run_id: str,
    environment: str = "local",
    instance_id: str = "level_06_nesting_fixture",
    random_seed: int = 42,
) -> None:
    """Persist one fixture adapter result without exposing a Level 6 runtime.

    The caller supplies a unique ``outputs/level_06/runs/<run_id>`` directory.
    Existing non-empty paths fail rather than overwriting prior evidence.
    """
    _assert_isolated_run_dir(run_dir)
    run_dir.mkdir(parents=True, exist_ok=False)
    metadata = _metadata(
        result, containers, config, run_id=run_id, environment=environment,
        instance_id=instance_id, random_seed=random_seed,
    )
    if result.validation is None:
        write_status_outputs(
            run_dir, metadata, config, items_path=items_path,
            containers_path=containers_path, project_root=project_root,
        )
        return
    write_run_outputs(
        run_dir,
        list(result.placements),
        containers,
        metadata,
        result.validation.result,
        config,
        items_path=items_path,
        containers_path=containers_path,
        project_root=project_root,
        extra_solution_tables=result.validation.solution_tables,
        extra_validation_documents=result.validation.validation_documents,
        solution_payload_extra=result.validation.solution_payload_extra,
        scene_item_metadata=result.validation.scene_item_metadata,
        extra_report_lines=result.validation.extra_report_lines,
    )


def _assert_isolated_run_dir(run_dir: Path) -> None:
    if run_dir.parent.name != "runs" or run_dir.parent.parent.name != "level_06":
        raise ValueError("Level 6 fixture output must be under outputs/level_06/runs/<run_id>")
    if run_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing Level 6 fixture run: {run_dir}")


def _metadata(
    result: Level06NestingFfdFixtureResult,
    containers: list[Container],
    config: dict[str, Any],
    *,
    run_id: str,
    environment: str,
    instance_id: str,
    random_seed: int,
) -> dict[str, Any]:
    placements = list(result.placements)
    selected = sorted({value.container_id for value in placements})
    total_cost = sum(value.cost for value in containers if value.container_id in selected)
    validation_metadata = {} if result.validation is None else result.validation.metadata
    return {
        "level_id": "level_06",
        "run_id": run_id,
        "algorithm_id": "extreme_point_ffd_nesting_fixture",
        "algorithm_role": "fixture_only_not_registered",
        "solver": result.outcome.backend,
        "solver_message": result.outcome.solve.message,
        "environment": environment,
        "instance_id": instance_id,
        "random_seed": random_seed,
        "status": result.outcome.solve.status,
        "objective_value": result.outcome.solve.objective_value,
        "algorithm_runtime_seconds": result.outcome.metadata.get("algorithm_runtime_seconds"),
        "n_items": result.item_count,
        "n_containers": len(containers),
        "container_count": len(selected),
        "total_container_cost": total_cost,
        "selected_containers": selected,
        "support_threshold": config.get("support", {}).get("threshold"),
        "active_constraints": [
            "compound_boundaries", "compound_payload", "compound_non_overlap",
            "exact_base_support", "base_center_support", "stackability",
            "static_load_bearing", "explicit_nesting_relations",
        ],
        "inactive_constraints": [
            "full_physical_stability", "internal_nesting_load_transfer",
            "orientation_aware_nesting", "nesting_aware_runtime_registry",
        ],
        **result.outcome.metadata,
        **validation_metadata,
    }
