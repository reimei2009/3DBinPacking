"""Opt-in sequential replay integration for generic Level 8 runtime runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from ..data_loader import load_config
from ..runtime.project import find_project_root
from ..schemas import Container, Item, Placement, SolveResult, ValidationIssue, ValidationResult
from .level_08_sequential_output import (
    validate_sequential_fixture_artifacts,
    write_sequential_fixture_artifacts,
)
from .level_08_sequential_planner import (
    SimulationPlan,
    build_deterministic_fixture_plan,
    simulation_metrics,
)
from .level_08_simulation_contract import SequentialSimulationSettings
from .nesting_engine import NestingRelation
from .pipeline import ValidationBundle


def sequential_runtime_options(config: dict[str, Any]) -> dict[str, Any]:
    value = config.get("sequential_simulation", {})
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValueError("sequential_simulation must be a mapping")
    enabled = bool(value.get("enabled", False))
    required = bool(value.get("required_when_enabled", True))
    rules_file = value.get("rules_file", "config/level_08/sequential_simulation_rules.yaml")
    if enabled and not isinstance(rules_file, str):
        raise ValueError("sequential_simulation.rules_file must be a path string")
    return {
        "enabled": enabled,
        "required_when_enabled": required,
        "rules_file": str(rules_file),
    }


def sequential_prevalidation_metadata(
    config: dict[str, Any],
    solve: SolveResult,
    placements: list[Placement],
    items: list[Item],
) -> dict[str, Any]:
    """Describe disabled/pending/skipped replay before final validation."""
    options = sequential_runtime_options(config)
    if not options["enabled"]:
        return {
            "sequential_simulation_enabled": False,
            "sequential_simulation_status": "DISABLED",
            "sequential_simulation_skip_reason": "disabled_by_config",
        }
    complete = (
        solve.status in {"OPTIMAL", "FEASIBLE", "FEASIBLE_TIME_LIMIT"}
        and len(placements) == len(items)
    )
    return {
        "sequential_simulation_enabled": True,
        "sequential_simulation_status": (
            "PENDING_STATIC_VALIDATION" if complete else "SKIPPED"
        ),
        "sequential_simulation_skip_reason": (
            None if complete else f"packing_status_{solve.status.lower()}"
        ),
    }


def load_sequential_rules(config: dict[str, Any]) -> dict[str, Any]:
    options = sequential_runtime_options(config)
    root = find_project_root(__file__)
    path = Path(options["rules_file"])
    return load_config(path if path.is_absolute() else root / path)


def build_generic_sequential_plan(
    items: Iterable[Item],
    containers: Iterable[Container],
    placements: Iterable[Placement],
    config: dict[str, Any],
    *,
    nesting_relations: Iterable[NestingRelation] = (),
) -> SimulationPlan:
    from .level_08_pipeline import unloading_rules

    return build_deterministic_fixture_plan(
        items,
        containers,
        placements,
        unloading_config=unloading_rules(config),
        simulation_config=load_sequential_rules(config),
        inherited_config=config,
        nesting_relations=nesting_relations,
    )


def compose_optional_sequential_validation(
    inherited: ValidationBundle,
    items: list[Item],
    containers: list[Container],
    placements: list[Placement],
    config: dict[str, Any],
) -> ValidationBundle:
    """Apply replay as a hard final gate only when explicitly enabled."""
    options = sequential_runtime_options(config)
    base_metadata = {
        "sequential_simulation_enabled": options["enabled"],
        "sequential_simulation_required_when_enabled": options["required_when_enabled"],
        "sequential_simulation_rules_file": options["rules_file"],
    }
    if not options["enabled"]:
        return _with_metadata(
            inherited,
            {
                **base_metadata,
                "sequential_simulation_status": "DISABLED",
                "sequential_simulation_skip_reason": "disabled_by_config",
            },
        )
    if not inherited.result.valid:
        return _with_metadata(
            inherited,
            {
                **base_metadata,
                "sequential_simulation_status": "SKIPPED",
                "sequential_simulation_skip_reason": "static_level_01_to_08_validation_invalid",
            },
        )
    try:
        plan = build_generic_sequential_plan(items, containers, placements, config)
        plan_validation = ValidationResult(
            plan.validation.result.valid,
            list(plan.validation.result.issues),
        )
    except (OSError, ValueError) as exc:
        plan = None
        plan_validation = ValidationResult(
            False,
            [ValidationIssue("SEQUENTIAL_REPLAY_BUILD_FAILED", str(exc))],
        )
    issues = [*inherited.result.issues, *plan_validation.issues]
    required_failure = options["required_when_enabled"] and not plan_validation.valid
    final_issues = issues if required_failure else list(inherited.result.issues)
    metadata = {
        **base_metadata,
        "sequential_simulation_status": "VALID" if plan_validation.valid else "INVALID",
        "sequential_simulation_skip_reason": None,
        "sequential_simulation_hard_gate": options["required_when_enabled"],
        "sequential_simulation_event_count": len(plan.events) if plan is not None else 0,
        "sequential_simulation_stop_count": (
            simulation_metrics(plan)["stop_count"] if plan is not None else 0
        ),
    }
    return ValidationBundle(
        ValidationResult(not final_issues, final_issues),
        solution_tables=inherited.solution_tables,
        validation_documents=inherited.validation_documents,
        solution_payload_extra=inherited.solution_payload_extra,
        scene_item_metadata=inherited.scene_item_metadata,
        extra_report_lines=[
            *inherited.extra_report_lines,
            (
                "- Level 8 deterministic sequential replay: "
                f"{metadata['sequential_simulation_status']}."
            ),
        ],
        metadata={**inherited.metadata, **metadata},
    )


def write_optional_sequential_artifacts(
    run_dir: Path,
    items: list[Item],
    containers: list[Container],
    placements: list[Placement],
    config: dict[str, Any],
    metadata: dict[str, Any],
    bundle: ValidationBundle,
) -> None:
    """Write seven artifacts only for an enabled, independently valid replay."""
    if not sequential_runtime_options(config)["enabled"]:
        return
    if not bundle.result.valid or metadata.get("sequential_simulation_status") != "VALID":
        return
    rules = load_sequential_rules(config)
    plan = build_generic_sequential_plan(items, containers, placements, config)
    write_sequential_fixture_artifacts(
        run_dir,
        plan,
        items,
        placements,
        SequentialSimulationSettings.from_config(rules),
    )


def validate_optional_sequential_artifacts(
    run_dir: Path,
    items: list[Item],
    containers: list[Container],
    placements: list[Placement],
    config: dict[str, Any],
) -> ValidationResult:
    options = sequential_runtime_options(config)
    if not options["enabled"]:
        return ValidationResult(True, [])
    try:
        rules = load_sequential_rules(config)
        plan = build_generic_sequential_plan(items, containers, placements, config)
        return validate_sequential_fixture_artifacts(
            run_dir,
            plan,
            SequentialSimulationSettings.from_config(rules),
        )
    except (OSError, ValueError) as exc:
        return ValidationResult(
            False,
            [ValidationIssue("SEQUENTIAL_REPLAY_REVALIDATION_FAILED", str(exc))],
        )


def _with_metadata(bundle: ValidationBundle, metadata: dict[str, Any]) -> ValidationBundle:
    return ValidationBundle(
        bundle.result,
        solution_tables=bundle.solution_tables,
        validation_documents=bundle.validation_documents,
        solution_payload_extra=bundle.solution_payload_extra,
        scene_item_metadata=bundle.scene_item_metadata,
        extra_report_lines=bundle.extra_report_lines,
        metadata={**bundle.metadata, **metadata},
    )
