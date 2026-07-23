"""Level 2 geometric-support strategy over the shared orchestration pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .level_01_preprocessing import validate_instance
from .level_02_algorithms import execute_level_02
from .level_02_validation import validate_solution
from .pipeline import LevelRuntimeStrategy, ValidationBundle, run_configured_level


def _guard(config: dict[str, Any]) -> None:
    model = config.get("model", {})
    if not bool(model.get("enforce_support", False)):
        raise ValueError("Level 2 requires model.enforce_support=true")
    forbidden = {
        "allow_rotation": model.get("allow_rotation", False),
        "enforce_stability": model.get("enforce_stability", False),
        "enforce_stackability": model.get("enforce_stackability", False),
    }
    enabled = [name for name, value in forbidden.items() if value]
    if enabled:
        raise ValueError(f"Level 2 support-only does not support enabled options: {', '.join(enabled)}")
    support = config.get("support", {})
    threshold = float(support.get("threshold", 0.8))
    if not 0 < threshold <= 1:
        raise ValueError("support.threshold must be in (0, 1]")
    for key in ("grid_x", "grid_y", "dense_grid_x", "dense_grid_y"):
        if int(support.get(key, 0)) <= 0:
            raise ValueError(f"support.{key} must be positive")
    if float(support.get("epsilon_mm", 0)) <= 0:
        raise ValueError("support.epsilon_mm must be positive")


def _validate(items, containers, placements, config) -> ValidationBundle:
    validation = config.get("validation", {})
    support = config["support"]
    details = validate_solution(
        items, containers, placements,
        support_threshold=float(support["threshold"]),
        support_epsilon_mm=float(support["epsilon_mm"]),
        dense_grid_x=int(support["dense_grid_x"]),
        dense_grid_y=int(support["dense_grid_y"]),
        coordinate_tolerance=float(validation.get("coordinate_tolerance_mm", 1e-4)),
        weight_tolerance=float(validation.get("weight_tolerance_kg", 1e-6)),
    )
    minimum_ratio = min((record.exact_support_ratio for record in details.support_records), default=1.0)
    return ValidationBundle(
        details.result,
        solution_tables={"support.csv": [record.to_dict() for record in details.support_records]},
        validation_documents={"support_validation.json": details.payload()},
        metadata={
            "support_threshold": details.threshold,
            "minimum_exact_support_ratio": minimum_ratio,
            "all_centers_supported": all(record.center_supported for record in details.support_records),
        },
    )


STRATEGY = LevelRuntimeStrategy(
    level_number=2,
    execute=execute_level_02,
    validate_instance=lambda items, containers, expected: validate_instance(items, containers, expected_items=expected),
    validate_solution=_validate,
    guard_config=_guard,
    active_constraints=(
        "exact_assignment", "container_activation", "boundaries", "payload",
        "direction_linking", "separation_activation", "pairwise_non_overlap",
        "aggregate_volume_capacity", "global_capacity_lower_bounds",
        "floor_contact", "support_top_contact", "support_grid_coverage", "base_center_support",
    ),
    inactive_constraints=(
        "rotation", "stackability", "load_bearing", "load_transfer", "physical_stability",
        "fragility", "center_of_gravity", "loading_order", "unloading_order",
    ),
    metadata_defaults={
        "rotation_enabled": False, "support_enabled": True, "stability_enabled": False,
        "stackability_enabled": False, "containers_data_status": "synthetic_level2",
    },
    algorithm_roles={
        "extreme_point_ffd": "practical_default",
        "milp_big_m": "exact_reference",
        "extreme_point_best_fit": "alternative_method",
        "extreme_point_hill_climbing": "alternative_method",
        "extreme_point_simulated_annealing": "alternative_method",
        "maximal_space_best_fit": "alternative_method",
    },
)


def run_from_config(
    config_path: str | Path, *, item_count: int | None = None, container_count: int | None = None,
    write_outputs: bool = True, level_id: str = "level_02", algorithm_id: str = "milp_big_m",
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
