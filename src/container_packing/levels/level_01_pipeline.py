"""Level 1 strategy over the reusable level orchestration pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..runtime.project import find_project_root
from .level_01_algorithms import execute_level_01
from .level_01_preprocessing import validate_instance
from .level_01_validation import validate_solution
from .pipeline import LevelRuntimeStrategy, ValidationBundle, run_configured_level


def project_root() -> Path:
    return find_project_root(__file__)


def _guard(config: dict[str, Any]) -> None:
    model = config.get("model", {})
    forbidden = {
        "allow_rotation": model.get("allow_rotation", False),
        "enforce_stability": model.get("enforce_stability", False),
        "enforce_stackability": model.get("enforce_stackability", False),
        "enforce_support": model.get("enforce_support", False),
    }
    enabled = [name for name, value in forbidden.items() if value]
    if enabled:
        raise ValueError(f"Level 1 does not support enabled options: {', '.join(enabled)}")


def _validate(items, containers, placements, config) -> ValidationBundle:
    settings = config.get("validation", {})
    return ValidationBundle(validate_solution(
        items, containers, placements,
        coordinate_tolerance=float(settings.get("coordinate_tolerance_mm", 1e-4)),
        weight_tolerance=float(settings.get("weight_tolerance_kg", 1e-6)),
    ))


STRATEGY = LevelRuntimeStrategy(
    level_number=1,
    execute=execute_level_01,
    validate_instance=lambda items, containers, expected: validate_instance(items, containers, expected_items=expected),
    validate_solution=_validate,
    guard_config=_guard,
    active_constraints=(
        "exact_assignment", "container_activation", "boundaries", "payload",
        "direction_linking", "separation_activation", "pairwise_non_overlap",
    ),
    inactive_constraints=("rotation", "stackability", "support", "stability", "fragility", "center_of_gravity"),
    metadata_defaults={
        "rotation_enabled": False, "support_enabled": False, "stability_enabled": False,
        "stackability_enabled": False, "containers_data_status": "synthetic_level1",
    },
)


def run_from_config(
    config_path: str | Path, *, item_count: int | None = None, container_count: int | None = None,
    write_outputs: bool = True, level_id: str = "level_01", algorithm_id: str = "milp_big_m",
    environment: str = "local", random_seed: int | None = None,
    algorithm_parameters: dict[str, Any] | None = None,
    config_overrides: dict[str, Any] | None = None,
    item_selection_strategy: str | None = None, item_selection_seed: int | None = None,
):
    return run_configured_level(
        config_path, strategy=STRATEGY, item_count=item_count, container_count=container_count,
        write_outputs=write_outputs, level_id=level_id, algorithm_id=algorithm_id,
        environment=environment, random_seed=random_seed, algorithm_parameters=algorithm_parameters,
        config_overrides=config_overrides,
        item_selection_strategy=item_selection_strategy, item_selection_seed=item_selection_seed,
    )
