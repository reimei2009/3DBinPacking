"""Isolated output writer for Level 7 validation-only fixture evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..reporting import write_run_outputs
from ..schemas import Container, Item, Placement
from .pipeline import ValidationBundle


def write_level_07_fixture_bundle_run(
    run_dir: Path,
    items: list[Item],
    containers: list[Container],
    placements: list[Placement],
    bundle: ValidationBundle,
    config: dict[str, Any],
    *,
    items_path: Path,
    containers_path: Path,
    project_root: Path,
    run_id: str,
    environment: str = "local",
    instance_id: str = "level_07_balance_fixture",
    random_seed: int = 42,
) -> None:
    """Persist validation evidence without registering or invoking a solver."""
    _assert_isolated_run_dir(run_dir)
    run_dir.mkdir(parents=True, exist_ok=False)
    write_run_outputs(
        run_dir,
        placements,
        containers,
        _metadata(
            items, containers, placements, bundle, config, run_id=run_id,
            environment=environment, instance_id=instance_id, random_seed=random_seed,
        ),
        bundle.result,
        config,
        items_path=items_path,
        containers_path=containers_path,
        project_root=project_root,
        extra_solution_tables=bundle.solution_tables,
        extra_validation_documents=bundle.validation_documents,
        solution_payload_extra=bundle.solution_payload_extra,
        scene_item_metadata=bundle.scene_item_metadata,
        extra_report_lines=bundle.extra_report_lines,
    )


def _assert_isolated_run_dir(run_dir: Path) -> None:
    if run_dir.parent.name != "runs" or run_dir.parent.parent.name != "level_07":
        raise ValueError("Level 7 fixture output must be under outputs/level_07/runs/<run_id>")
    if run_dir.exists():
        raise FileExistsError(f"Refusing to overwrite existing Level 7 fixture run: {run_dir}")


def _metadata(
    items: list[Item],
    containers: list[Container],
    placements: list[Placement],
    bundle: ValidationBundle,
    config: dict[str, Any],
    *,
    run_id: str,
    environment: str,
    instance_id: str,
    random_seed: int,
) -> dict[str, Any]:
    selected = sorted({value.container_id for value in placements})
    total_cost = sum(value.cost for value in containers if value.container_id in selected)
    return {
        "level_id": "level_07",
        "run_id": run_id,
        "algorithm_id": "level_07_fixture_validation_bundle",
        "algorithm_role": "fixture_only_not_registered",
        "solver": "not_applicable_validation_only",
        "solver_message": "Level 7 fixture validation bundle; no solver was invoked.",
        "environment": environment,
        "instance_id": instance_id,
        "random_seed": random_seed,
        "status": "VALIDATION_ONLY",
        "objective_value": None,
        "n_items": len(items),
        "n_containers": len(containers),
        "container_count": len(selected),
        "total_container_cost": total_cost,
        "selected_containers": selected,
        "support_threshold": config.get("support", {}).get("threshold"),
        "active_constraints": [
            "compound_boundaries", "compound_payload", "compound_non_overlap",
            "exact_base_support", "base_center_support", "stackability",
            "static_load_bearing", "explicit_nesting_relations",
            "compound_root_center_of_mass_balance",
        ],
        "inactive_constraints": [
            "level_07_solver", "floor_zone_load_limits", "door_clearance",
            "axle_load_limits", "dynamic_transport_load", "rollover_stability",
        ],
        **bundle.metadata,
    }
