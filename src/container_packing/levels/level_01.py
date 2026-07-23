"""Level 1 adapter: fixed orientation, boundaries, non-overlap, and payload."""

from __future__ import annotations

from pathlib import Path

from ..data_loader import load_config, load_containers, load_items, load_placements
from ..experiments.contracts import ExperimentRequest
from ..instance_data import prepare_instance
from .level_01_pipeline import project_root, run_from_config
from .level_01_validation import validate_solution


def run(request: ExperimentRequest):
    return run_from_config(
        request.config_path,
        item_count=request.item_count,
        container_count=request.container_count,
        level_id=request.level_id,
        algorithm_id=request.algorithm_id,
        environment=request.environment,
        random_seed=request.random_seed,
        algorithm_parameters=request.algorithm_parameters,
        config_overrides=request.config_overrides,
        item_selection_strategy=request.item_selection_strategy,
        item_selection_seed=request.item_selection_seed,
    )


def prepare(request: ExperimentRequest) -> dict:
    return prepare_instance(
        project_root(), load_config(request.config_path),
        item_count=request.item_count, container_count=request.container_count,
        level_id=request.level_id,
        item_selection_strategy=request.item_selection_strategy,
        item_selection_seed=request.item_selection_seed,
    )


def validate_run(run_dir: Path):
    items = load_items(run_dir / "input_snapshot" / "items.csv")
    containers = load_containers(run_dir / "input_snapshot" / "containers.csv")
    placements = load_placements(run_dir / "solution" / "placements.csv")
    return validate_solution(items, containers, placements)
