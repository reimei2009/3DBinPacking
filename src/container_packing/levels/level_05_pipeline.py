"""Level 5 static load-bearing pipeline over the Level 4 contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..data_loader import load_config
from ..runtime.project import find_project_root
from ..schemas import ValidationResult
from .level_03_preprocessing import validate_instance
from .level_04_pipeline import _guard as guard_level_04
from .level_04_pipeline import _rules as stackability_rules
from .level_04_pipeline import _validate as validate_level_04
from .level_05_algorithms import execute_level_05
from .level_05_validation import Level05LoadValidation, validate_load_bearing
from .load_bearing import LoadBearingSettings
from .pipeline import LevelRuntimeStrategy, ValidationBundle, run_configured_level


def load_bearing_rules(config: dict[str, Any]) -> dict[str, Any]:
    value = config.get("load_bearing", {})
    if "contract_version" in value:
        return value
    rules_file = value.get("rules_file")
    if not rules_file:
        raise ValueError("Level 5 requires load_bearing.rules_file")
    root = find_project_root(__file__)
    path = Path(str(rules_file))
    loaded = load_config(path if path.is_absolute() else root / path)
    config["load_bearing"] = {**loaded, "rules_file": str(rules_file)}
    return config["load_bearing"]


def _guard(config: dict[str, Any]) -> None:
    guard_level_04(config)
    model = config.get("model", {})
    if not bool(model.get("enforce_load_bearing", False)):
        raise ValueError("Level 5 requires model.enforce_load_bearing=true")
    if not bool(model.get("enforce_load_transfer", False)):
        raise ValueError("Level 5 requires model.enforce_load_transfer=true")
    LoadBearingSettings.from_config(load_bearing_rules(config))
    tolerance = float(config.get("validation", {}).get("load_tolerance_kg", 1e-6))
    if tolerance < 0:
        raise ValueError("validation.load_tolerance_kg must be non-negative")


def _load_metadata(details: Level05LoadValidation) -> dict[str, Any]:
    ratios = [
        record.load_utilization_ratio
        for record in details.records
        if record.load_utilization_ratio is not None
    ]
    margins = [record.safety_margin_kg for record in details.records]
    return {
        "maximum_load_utilization_ratio": max(ratios, default=0.0),
        "minimum_load_safety_margin_kg": min(margins, default=0.0),
        "fragile_item_count": sum(record.is_fragile for record in details.records),
        "overloaded_item_count": sum(
            record.load_above_kg > record.max_supported_weight_kg
            for record in details.records
        ),
        "load_transfer_edge_count": len(details.edges),
    }


def validate_level_05_bundle(items, containers, placements, config) -> ValidationBundle:
    level_04 = validate_level_04(items, containers, placements, config)
    support = config["support"]
    rules = load_bearing_rules(config)
    load_details = validate_load_bearing(
        items,
        placements,
        rules,
        epsilon_mm=float(support["epsilon_mm"]),
        load_tolerance_kg=float(
            config.get("validation", {}).get("load_tolerance_kg", 1e-6)
        ),
    )
    issues = [*level_04.result.issues, *load_details.result.issues]
    combined_result = ValidationResult(not issues, issues)
    load_records = [record.to_dict() for record in load_details.records]
    load_edges = [edge.to_dict() for edge in load_details.edges]
    load_by_item = {record.item_id: record for record in load_details.records}
    scene_metadata = {
        item_id: dict(metadata)
        for item_id, metadata in level_04.scene_item_metadata.items()
    }
    for item_id, record in load_by_item.items():
        scene_metadata.setdefault(item_id, {}).update(
            {
                "load_above_kg": record.load_above_kg,
                "max_supported_weight_kg": record.max_supported_weight_kg,
                "load_utilization_ratio": record.load_utilization_ratio,
                "is_fragile": record.is_fragile,
            }
        )
    load_metadata = _load_metadata(load_details)
    return ValidationBundle(
        combined_result,
        solution_tables={
            **level_04.solution_tables,
            "load_bearing.csv": load_records,
            "load_transfer.csv": load_edges,
        },
        validation_documents={
            **level_04.validation_documents,
            "load_bearing_validation.json": load_details.payload(),
        },
        solution_payload_extra={
            **level_04.solution_payload_extra,
            "load_bearing": {
                "model": "static_vertical_contact_area_recursive_v1",
                "records": load_records,
                "edges": load_edges,
            },
        },
        scene_item_metadata=scene_metadata,
        extra_report_lines=[
            *level_04.extra_report_lines,
            f"- Maximum load utilization: {load_metadata['maximum_load_utilization_ratio']:.4f}",
            f"- Minimum load safety margin: {load_metadata['minimum_load_safety_margin_kg']:.3f} kg",
            f"- Load-transfer edges: {load_metadata['load_transfer_edge_count']}",
        ],
        metadata={
            **level_04.metadata,
            "load_bearing_contract_version": rules["contract_version"],
            "load_bearing_data_status": rules["data_status"],
            "load_bearing_capacity_profile": rules["capacity_profile"]["mode"],
            "load_transfer_model": "static_vertical_contact_area_recursive_v1",
            **load_metadata,
        },
    )


STRATEGY = LevelRuntimeStrategy(
    level_number=5,
    execute=execute_level_05,
    validate_instance=lambda items, containers, expected: validate_instance(
        items, containers, expected_items=expected
    ),
    validate_solution=validate_level_05_bundle,
    guard_config=_guard,
    active_constraints=(
        "single_assignment", "container_activation", "bounds", "non_overlap",
        "payload", "horizontal_orientation", "floor_contact",
        "minimum_exact_support_ratio", "base_center_support",
        "stackability_same_group", "maximum_stack_layers",
        "recursive_static_load_transfer", "maximum_supported_weight",
        "fragile_no_supported_load",
    ),
    inactive_constraints=(
        "vertical_axis_rotation", "pressure", "contact_moments",
        "dynamic_load", "load_balance", "nesting", "loading_order",
        "unloading_order",
    ),
    metadata_defaults={
        "solution_claim": (
            "Geometry, payload, support, horizontal-orientation, stackability, "
            "and static load-bearing feasible under Level 5 research assumptions."
        ),
        "rotation_enabled": True,
        "rotation_mode": "horizontal_only",
        "support_enabled": True,
        "stackability_enabled": True,
        "physical_stability_claim": False,
        "load_bearing_enabled": True,
        "load_transfer_enabled": True,
        "stability_enabled": False,
        "containers_data_status": "synthetic_level5",
        "load_bearing_scope": "static_vertical_contact_area_recursive_research_profile",
    },
    algorithm_roles={
        "extreme_point_best_fit": "practical_default",
        "extreme_point_ffd": "constructive_comparator",
        "extreme_point_hill_climbing": "local_search_comparator",
        "extreme_point_simulated_annealing": "metaheuristic_comparator",
    },
)


def run_from_config(
    config_path: str | Path,
    *,
    item_count: int | None = None,
    container_count: int | None = None,
    write_outputs: bool = True,
    level_id: str = "level_05",
    algorithm_id: str = "extreme_point_best_fit",
    environment: str = "local",
    random_seed: int | None = None,
    algorithm_parameters: dict[str, Any] | None = None,
    config_overrides: dict[str, Any] | None = None,
    item_selection_strategy: str | None = None,
    item_selection_seed: int | None = None,
):
    return run_configured_level(
        config_path,
        strategy=STRATEGY,
        item_count=item_count,
        container_count=container_count,
        write_outputs=write_outputs,
        level_id=level_id,
        algorithm_id=algorithm_id,
        environment=environment,
        random_seed=random_seed,
        algorithm_parameters=algorithm_parameters,
        config_overrides=config_overrides,
        item_selection_strategy=item_selection_strategy,
        item_selection_seed=item_selection_seed,
    )
