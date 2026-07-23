"""Level 2 adapter: Level 1 geometry/payload plus geometric support."""

from __future__ import annotations

from pathlib import Path

import yaml

from ..data_loader import load_config, load_containers, load_items, load_placements
from ..experiments.contracts import ExperimentRequest
from ..instance_data import prepare_instance
from ..runtime.project import find_project_root
from .level_02_pipeline import run_from_config
from .level_02_validation import validate_solution


def run(request: ExperimentRequest):
    return run_from_config(
        request.config_path, item_count=request.item_count, container_count=request.container_count,
        level_id=request.level_id, algorithm_id=request.algorithm_id, environment=request.environment,
        random_seed=request.random_seed, algorithm_parameters=request.algorithm_parameters,
        config_overrides=request.config_overrides,
        item_selection_strategy=request.item_selection_strategy, item_selection_seed=request.item_selection_seed,
    )


def prepare(request: ExperimentRequest) -> dict:
    return prepare_instance(
        find_project_root(__file__), load_config(request.config_path), item_count=request.item_count,
        container_count=request.container_count, level_id=request.level_id,
        item_selection_strategy=request.item_selection_strategy, item_selection_seed=request.item_selection_seed,
    )


def validate_run(run_dir: Path):
    config = yaml.safe_load((run_dir / "resolved_config.yaml").read_text(encoding="utf-8"))
    support = config["support"]
    details = validate_solution(
        load_items(run_dir / "input_snapshot/items.csv"),
        load_containers(run_dir / "input_snapshot/containers.csv"),
        load_placements(run_dir / "solution/placements.csv"),
        support_threshold=float(support["threshold"]), support_epsilon_mm=float(support["epsilon_mm"]),
        dense_grid_x=int(support["dense_grid_x"]), dense_grid_y=int(support["dense_grid_y"]),
        coordinate_tolerance=float(config["validation"]["coordinate_tolerance_mm"]),
        weight_tolerance=float(config["validation"]["weight_tolerance_kg"]),
    )
    return details.result
