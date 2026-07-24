"""Level 4 stackability strategy over the shared orientation/support pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..data_loader import load_config
from ..runtime.project import find_project_root
from .level_03_preprocessing import validate_instance
from .level_04_algorithms import execute_level_04
from .level_04_validation import validate_solution
from .pipeline import LevelRuntimeStrategy, ValidationBundle, run_configured_level
from .stackability import (
    StackabilitySettings,
    attributes_for_item,
    infer_parent_relations,
    report_lines,
    scene_item_metadata,
    solution_payload,
)


def _rules(config: dict[str, Any]) -> dict[str, Any]:
    value = config.get("stackability", {})
    if "contract_version" in value:
        return value
    rules_file = value.get("rules_file")
    if not rules_file:
        raise ValueError("Level 4 requires stackability.rules_file")
    root = find_project_root(__file__)
    path = Path(str(rules_file))
    loaded = load_config(path if path.is_absolute() else root / path)
    config["stackability"] = {**loaded, "rules_file": str(rules_file)}
    return config["stackability"]


def _guard(config: dict[str, Any]) -> None:
    model = config.get("model", {})
    if not bool(model.get("allow_rotation", False)):
        raise ValueError("Level 4 requires model.allow_rotation=true")
    if not bool(model.get("enforce_support", False)):
        raise ValueError("Level 4 requires model.enforce_support=true")
    if not bool(model.get("enforce_stackability", False)):
        raise ValueError("Level 4 requires model.enforce_stackability=true")
    if bool(model.get("enforce_stability", False)):
        raise ValueError("Level 4 does not support model.enforce_stability=true")
    if config.get("orientation", {}).get("profile") != "horizontal_rotatable":
        raise ValueError("Level 4 requires orientation.profile='horizontal_rotatable'")
    support = config.get("support", {})
    if not 0 < float(support.get("threshold", 0.0)) <= 1:
        raise ValueError("support.threshold must be in (0, 1]")
    if float(support.get("epsilon_mm", 0.0)) <= 0:
        raise ValueError("support.epsilon_mm must be positive")
    StackabilitySettings.from_config(_rules(config))


def _validate(items, containers, placements, config) -> ValidationBundle:
    validation = config.get("validation", {})
    support = config["support"]
    rules = _rules(config)
    settings = StackabilitySettings.from_config(rules)
    attributes = {item.item_id: attributes_for_item(item, settings) for item in items}
    relations = infer_parent_relations(
        placements, attributes, epsilon_mm=float(support["epsilon_mm"]),
    )
    details = validate_solution(
        items, containers, placements, relations, rules,
        support_threshold=float(support["threshold"]),
        support_epsilon_mm=float(support["epsilon_mm"]),
        coordinate_tolerance=float(validation.get("coordinate_tolerance_mm", 1e-4)),
        weight_tolerance=float(validation.get("weight_tolerance_kg", 1e-6)),
    )
    records = details.stack_records
    minimum_ratio = min((record.exact_support_ratio for record in details.support_validation.support_records), default=1.0)
    return ValidationBundle(
        details.result,
        solution_tables={
            "support.csv": [record.to_dict() for record in details.support_validation.support_records],
            "stacks.csv": [record.to_dict() for record in records],
        },
        validation_documents={
            "support_validation.json": details.support_validation.payload(),
            "stack_validation.json": details.payload(),
        },
        solution_payload_extra={"stackability": solution_payload(records)},
        scene_item_metadata=scene_item_metadata(records),
        extra_report_lines=report_lines(records),
        metadata={
            "support_threshold": details.support_validation.threshold,
            "minimum_exact_support_ratio": minimum_ratio,
            "all_centers_supported": all(record.center_supported for record in details.support_validation.support_records),
            "orientation_profile": details.support_validation.orientation_profile,
            "orientation_data_status": "synthetic_orientation_profile",
            "stackability_contract_version": rules["contract_version"],
            "stackability_data_status": rules["data_status"],
            "stack_count": solution_payload(records)["stack_count"],
            "maximum_stack_depth": solution_payload(records)["maximum_stack_depth"],
        },
    )


STRATEGY = LevelRuntimeStrategy(
    level_number=4,
    execute=execute_level_04,
    validate_instance=lambda items, containers, expected: validate_instance(items, containers, expected_items=expected),
    validate_solution=_validate,
    guard_config=_guard,
    active_constraints=(
        "exact_assignment", "container_activation", "boundaries", "payload", "pairwise_non_overlap",
        "floor_contact", "support_top_contact", "support_exact_union_area", "base_center_support",
        "horizontal_orientation_selection", "stackability_same_group", "declared_direct_stack_parent",
        "maximum_stack_layers", "non_stackable_floor_root",
    ),
    inactive_constraints=(
        "vertical_axis_rotation", "load_bearing", "load_transfer", "physical_stability", "fragility",
        "center_of_gravity", "loading_order", "unloading_order", "nesting",
    ),
    metadata_defaults={
        "rotation_enabled": True, "rotation_mode": "horizontal_only", "support_enabled": True,
        "stackability_enabled": True, "load_bearing_enabled": False, "load_transfer_enabled": False,
        "stability_enabled": False, "containers_data_status": "synthetic_level4",
    },
    algorithm_roles={
        "extreme_point_best_fit": "practical_default",
        "extreme_point_ffd": "constructive_comparator",
        "maximal_space_best_fit": "constructive_comparator",
        "extreme_point_hill_climbing": "local_search_comparator",
        "extreme_point_simulated_annealing": "metaheuristic_comparator",
    },
)


def run_from_config(
    config_path: str | Path,
    *, item_count: int | None = None, container_count: int | None = None,
    write_outputs: bool = True, level_id: str = "level_04", algorithm_id: str = "extreme_point_best_fit",
    environment: str = "local", random_seed: int | None = None,
    algorithm_parameters: dict[str, Any] | None = None, config_overrides: dict[str, Any] | None = None,
    item_selection_strategy: str | None = None, item_selection_seed: int | None = None,
):
    return run_configured_level(
        config_path, strategy=STRATEGY, item_count=item_count, container_count=container_count,
        write_outputs=write_outputs, level_id=level_id, algorithm_id=algorithm_id, environment=environment,
        random_seed=random_seed, algorithm_parameters=algorithm_parameters, config_overrides=config_overrides,
        item_selection_strategy=item_selection_strategy, item_selection_seed=item_selection_seed,
    )
