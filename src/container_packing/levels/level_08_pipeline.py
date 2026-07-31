"""Config-driven Level 8 constructive runtime over the inherited Level 7 stack."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any

from ..algorithms.heuristics.extreme_point_best_fit import solve as solve_best_fit
from ..algorithms.heuristics.extreme_point_ffd import solve as solve_ffd
from ..data_loader import load_config
from ..schemas import ValidationResult
from ..schemas import SolveResult
from .level_03_preprocessing import validate_instance
from .level_06_compound_adapter import _expand_logical_members
from .level_06_compound_policy import build_level_06_compound_fixture_policy
from .level_06_pipeline import _guard as guard_level_06
from .level_07_fixture_bundle import balance_rules, validate_level_07_fixture_bundle
from .level_07_two_stage import solve_two_stage_balance
from .level_08_delivery_scoring import (
    DeliveryAwareCandidateScoringPolicy,
    DeliveryAwareFirstFitCandidateSelection,
    DeliveryDoorPointProvider,
    SequentialBalanceFeasibilityPolicy,
    StrictLifoFeasibilityPolicy,
)
from .level_08_validation import compose_level_08_validation, validate_unloading_lifo
from .level_08_delivery_repair import DeliveryRepairEngine
from .level_08_sequential_runtime import (
    compose_optional_sequential_validation,
    sequential_prevalidation_metadata,
    sequential_runtime_options,
    write_optional_sequential_artifacts,
)
from .pipeline import LevelRuntimeStrategy, run_configured_level
from .unloading import UnloadingSettings, delivery_attributes_for_item
from .nesting_runtime import compound_to_external_item, compound_to_external_placement


BEST_FIT_ALGORITHM_ID = "extreme_point_best_fit_delivery"
FFD_ALGORITHM_ID = "extreme_point_ffd_delivery"
ALGORITHM_IDS = (BEST_FIT_ALGORITHM_ID, FFD_ALGORITHM_ID)


def unloading_rules(config: dict[str, Any]) -> dict[str, Any]:
    value = config.get("unloading", {})
    if "contract_version" in value:
        return value
    rules_file = value.get("rules_file") if isinstance(value, dict) else None
    if not rules_file:
        raise ValueError("Level 8 runtime requires unloading.rules_file")
    root = Path(__file__).resolve().parents[3]
    loaded = load_config(root / str(rules_file))
    config["unloading"] = {**loaded, "rules_file": str(rules_file)}
    return config["unloading"]


def _guard(config: dict[str, Any]) -> None:
    guard_level_06({
        **config,
        "project": {**config.get("project", {}), "level_id": "level_06", "algorithm_id": "extreme_point_ffd_nesting_fixture"},
    })
    if config.get("project", {}).get("level_id") != "level_08":
        raise ValueError("Level 8 runtime requires project.level_id='level_08'")
    if config.get("project", {}).get("algorithm_id") not in ALGORITHM_IDS:
        raise ValueError("Level 8 runtime exposes only delivery-aware Best Fit and FFD")
    if not bool(config.get("model", {}).get("enforce_balance", False)):
        raise ValueError("Level 8 runtime requires inherited Level 7 balance validation")
    UnloadingSettings.from_config(unloading_rules(config))
    sequential_runtime_options(config)


def _validate_delivery_instance(items, containers, expected: int) -> None:
    validate_instance(items, containers, expected_items=expected)
    attributes = [delivery_attributes_for_item(item) for item in items]
    inactive = [value.item_id for value in attributes if not value.declared_active]
    if inactive:
        raise ValueError("Level 8 requires declared delivery metadata for every selected item: " + ", ".join(inactive))
    by_priority: dict[int, set[str]] = {}
    for value in attributes:
        assert value.delivery_priority is not None and value.delivery_stop_id is not None
        by_priority.setdefault(value.delivery_priority, set()).add(value.delivery_stop_id)
    ambiguous = [str(priority) for priority, stops in sorted(by_priority.items()) if len(stops) > 1]
    if ambiguous:
        raise ValueError("Each delivery_priority must map to one delivery_stop_id; ambiguous priorities: " + ", ".join(ambiguous))


def _execute(algorithm_id: str, items, containers, settings: dict[str, Any]):
    pipeline_started = perf_counter()
    pipeline_limit = max(0.0, float(settings.get("delivery_pipeline_time_limit_seconds", 45)))
    pipeline_deadline = pipeline_started + pipeline_limit
    rules = unloading_rules(settings)
    unloading = UnloadingSettings.from_config(rules)
    if algorithm_id == BEST_FIT_ALGORITHM_ID:
        def solver(compounds, available, config, **kwargs):
            base_policy = kwargs.pop("policy")
            use_sequential_balance = bool(
                config.get("sequential_balance_construction_enabled", False)
            )
            balance_config = (
                balance_rules(config) if use_sequential_balance else None
            )
            policy = StrictLifoFeasibilityPolicy(
                {item.item_id: item for item in compounds},
                unloading,
                base_policy,
            )
            if balance_config is not None:
                policy = SequentialBalanceFeasibilityPolicy(
                    balance_config, policy
                )
            return solve_best_fit(
                compounds, available, config,
                policy=policy,
                candidate_scoring_policy=DeliveryAwareCandidateScoringPolicy(
                    {item.item_id: item for item in compounds},
                    unloading,
                    balance_config,
                ),
                candidate_point_provider=DeliveryDoorPointProvider(
                    unloading, balance_config
                ),
                **kwargs,
            )
    elif algorithm_id == FFD_ALGORITHM_ID:
        def solver(compounds, available, config, **kwargs):
            base_policy = kwargs.pop("policy")
            use_sequential_balance = bool(
                config.get("sequential_balance_construction_enabled", False)
            )
            balance_config = (
                balance_rules(config) if use_sequential_balance else None
            )
            policy = StrictLifoFeasibilityPolicy(
                {item.item_id: item for item in compounds},
                unloading,
                base_policy,
            )
            if balance_config is not None:
                policy = SequentialBalanceFeasibilityPolicy(
                    balance_config, policy
                )
            return solve_ffd(
                compounds, available, config,
                policy=policy,
                candidate_selection_policy=DeliveryAwareFirstFitCandidateSelection(
                    {item.item_id: item for item in compounds},
                    unloading,
                    balance_config,
                ),
                candidate_point_provider=DeliveryDoorPointProvider(
                    unloading, balance_config
                ),
                **kwargs,
            )
    else:
        raise ValueError(f"Unsupported Level 8 algorithm: {algorithm_id}")
    def construct_balance_valid(source_settings: dict[str, Any]):
        """Build the compact delivery candidate, then apply Level 7 repair.

        Level 8 may only enter static LIFO and sequential replay from a
        balance-valid Level 1--7 state.  Reusing the canonical two-stage
        engine avoids treating the Level 7 validator as a passive final gate.
        """
        remaining = max(0.0, pipeline_deadline - perf_counter())
        return solve_two_stage_balance(
            items,
            containers,
            {
                **source_settings,
                "balance_pipeline_time_limit_seconds": remaining,
                "balance_repair_time_limit_seconds": remaining,
            },
            algorithm_id=algorithm_id,
            baseline_solver=solver,
            additional_candidate_validator=lambda placements: validate_unloading_lifo(
                items,
                placements,
                rules,
                tolerance_mm=float(
                    source_settings.get("coordinate_tolerance_mm", 1e-6)
                ),
            ).result.valid,
        )
    construction_mode = str(settings.get("delivery_construction_mode", "compact_then_delivery_priority"))
    compare_max_items = int(settings.get("delivery_construction_compare_max_items", 100))
    if construction_mode not in {"compact_then_delivery_priority", "delivery_priority_primary"}:
        raise ValueError("delivery_construction_mode must be compact_then_delivery_priority or delivery_priority_primary")
    compact_settings = {**settings, "constructive_deadline_monotonic": pipeline_deadline}
    delivery_settings = _delivery_priority_settings(compact_settings)
    construction_records: list[dict[str, object]] = []
    if construction_mode == "delivery_priority_primary":
        baseline = construct_balance_valid(delivery_settings)
        construction_records.append(_construction_record("delivery_priority_primary", baseline, items, rules, settings))
    else:
        baseline = construct_balance_valid(compact_settings)
        construction_records.append(_construction_record("compact_baseline", baseline, items, rules, settings))
        if (
            len(items) <= compare_max_items
            and baseline.outcome.solve.status == "FEASIBLE"
            and baseline.validation is not None
            and baseline.validation.result.valid
            and not validate_unloading_lifo(items, list(baseline.placements), rules).result.valid
        ):
            delivery_candidate = construct_balance_valid(delivery_settings)
            construction_records.append(_construction_record("delivery_priority_compare", delivery_candidate, items, rules, settings))
            if _construction_rank(delivery_candidate, items, rules, settings) < _construction_rank(baseline, items, rules, settings):
                baseline = delivery_candidate
    baseline_seconds = perf_counter() - pipeline_started
    remaining_seconds = max(0.0, pipeline_limit - baseline_seconds)
    baseline.outcome.metadata.update({
        "delivery_pipeline_time_limit_seconds": pipeline_limit,
        "delivery_baseline_runtime_seconds": baseline_seconds,
        "delivery_construction_mode_requested": construction_mode,
        "delivery_construction_mode_selected": construction_records[-1]["mode"] if len(construction_records) == 1 else (
            "delivery_priority_compare" if baseline is not None and baseline.outcome.metadata.get("compound_item_ordering") != "default_algorithm_order" else "compact_baseline"
        ),
        "delivery_construction_candidates": construction_records,
        "delivery_construction_compare_skipped_for_scale": bool(
            construction_mode == "compact_then_delivery_priority" and len(items) > compare_max_items
        ),
        "delivery_repair_time_limit_seconds": remaining_seconds,
        "delivery_repair_fixed_subset_seconds": float(settings.get("delivery_repair_fixed_subset_seconds", 35)),
        "delivery_repair_extra_container_seconds": float(settings.get("delivery_repair_extra_container_seconds", 10)),
        "delivery_repair_max_candidates": int(settings.get("delivery_repair_max_candidates", 256)),
        "delivery_repair_contributor_limit": int(settings.get("delivery_repair_contributor_limit", 8)),
        "delivery_repair_relocation_transfer_max_candidates": _optional_int(settings, "delivery_repair_relocation_transfer_max_candidates"),
        "delivery_repair_swap_max_candidates": _optional_int(settings, "delivery_repair_swap_max_candidates"),
        "delivery_repair_neighborhood_max_candidates": _optional_int(settings, "delivery_repair_neighborhood_max_candidates"),
        "delivery_repair_neighborhood_sizes": list(settings.get("delivery_repair_neighborhood_sizes", [4, 8, 12])),
        "delivery_repair_operator_time_fractions": list(settings.get("delivery_repair_operator_time_fractions", [0.5, 0.25, 0.25])),
        "delivery_repair_extra_max_candidates": _optional_int(settings, "delivery_repair_extra_max_candidates"),
        "delivery_repair_max_extra_containers": int(settings.get("delivery_repair_max_extra_containers", 1)),
    })
    if baseline.outcome.solve.status == "TIME_LIMIT" or perf_counter() >= pipeline_deadline:
        _mark_construction_time_limit(baseline, pipeline_limit, baseline_seconds)
        return baseline.outcome
    if baseline.outcome.solve.status != "FEASIBLE" or baseline.validation is None or not baseline.validation.result.valid:
        baseline.outcome.metadata.update({
            "delivery_repair_phase": "skipped_inherited_validation_failed",
            "delivery_outcome_class": "NO_VALID_LIFO_SOLUTION_WITHIN_BUDGET",
        })
        return baseline.outcome
    initial_unloading = validate_unloading_lifo(
        items, list(baseline.placements), rules,
        tolerance_mm=float(settings.get("coordinate_tolerance_mm", 1e-6)),
    )
    if initial_unloading.result.valid:
        baseline.outcome.metadata.update({
            "delivery_repair_phase": "baseline_valid",
            "delivery_repair_candidates_evaluated": 0,
            "delivery_repair_termination_reason": "baseline_already_lifo_valid",
            "delivery_outcome_class": "VALID_FIXED_CONTAINER",
        })
        return baseline.outcome
    repaired = _repair_delivery_order(
        items, containers, settings, rules, baseline,
        repair_seconds=remaining_seconds, pipeline_started=pipeline_started,
    )
    return repaired.outcome


def _repair_delivery_order(
    items, containers, settings, rules, baseline, *, repair_seconds: float,
    pipeline_started: float,
):
    """Repair only LIFO contributors; never perform a full instance rebuild."""
    started = perf_counter()
    if baseline.projection is None:
        return baseline
    original_by_id = {item.item_id: item for item in items}
    roots = [compound_to_external_placement(value) for value in baseline.projection.compounds]
    root_items = [
        compound_to_external_item(value, original_by_id[value.root_item_id])
        for value in baseline.projection.compounds
    ]
    used_ids = {value.container_id for value in roots}
    fixed = [value for value in containers if value.container_id in used_ids]
    unused = [value for value in containers if value.container_id not in used_ids]
    requested_extra_seconds = max(
        0.0, float(settings.get("delivery_repair_extra_container_seconds", 10))
    )
    # Reserve rescue time before allocating the fixed-container phase.
    extra_seconds = min(max(0.0, repair_seconds), requested_extra_seconds)
    fixed_seconds = min(
        max(0.0, repair_seconds - extra_seconds),
        max(0.0, float(settings.get("delivery_repair_fixed_subset_seconds", 35))),
    )
    tolerance = float(settings.get("coordinate_tolerance_mm", 1e-6))

    def inherited_valid(candidate_roots):
        expanded, resolved = _expand_logical_members(items, candidate_roots, baseline.relations)
        return validate_level_07_fixture_bundle(items, containers, expanded, settings, list(resolved)).result.valid

    def final_valid(candidate_roots):
        if not inherited_valid(candidate_roots):
            return False
        expanded, _ = _expand_logical_members(items, candidate_roots, baseline.relations)
        return validate_unloading_lifo(items, expanded, rules, tolerance_mm=tolerance).result.valid

    engine = DeliveryRepairEngine(
        policy=build_level_06_compound_fixture_policy(root_items, settings),
        settings=UnloadingSettings.from_config(rules),
        coordinate_tolerance_mm=tolerance,
        support_epsilon_mm=float(settings["support"]["epsilon_mm"]),
        max_candidates=int(settings.get("delivery_repair_max_candidates", 256)),
        contributor_limit=int(settings.get("delivery_repair_contributor_limit", 8)),
        relocation_transfer_max_candidates=_optional_int(settings, "delivery_repair_relocation_transfer_max_candidates"),
        swap_max_candidates=_optional_int(settings, "delivery_repair_swap_max_candidates"),
        neighborhood_max_candidates=_optional_int(settings, "delivery_repair_neighborhood_max_candidates"),
        extra_max_candidates=_optional_int(settings, "delivery_repair_extra_max_candidates"),
        neighborhood_sizes=tuple(int(value) for value in settings.get("delivery_repair_neighborhood_sizes", [4, 8, 12])),
        operator_time_fractions=tuple(float(value) for value in settings.get("delivery_repair_operator_time_fractions", [0.5, 0.25, 0.25])),
    )
    repaired = engine.repair(
        root_items, fixed, roots, validate_inherited=inherited_valid, validate_final=final_valid,
        fixed_seconds=fixed_seconds, extra_seconds=extra_seconds,
        extra_container=(unused[0] if int(settings.get("delivery_repair_max_extra_containers", 1)) > 0 and unused else None),
    )
    metadata = {
        **repaired.stats.metadata(),
        "delivery_repair_runtime_seconds": perf_counter() - started,
        "delivery_pipeline_runtime_seconds": perf_counter() - pipeline_started,
        "delivery_repair_initial_container_count": len(used_ids),
        "delivery_repair_final_container_count": len({value.container_id for value in repaired.best_inherited_valid_placements}),
    }
    if repaired.placements is None:
        baseline.outcome.metadata.update({
            **metadata,
            "delivery_repair_phase": "local_repair_exhausted",
            "delivery_outcome_class": "NO_VALID_LIFO_SOLUTION_WITHIN_BUDGET",
            "hide_objective_when_invalid": True,
        })
        return baseline
    expanded, resolved = _expand_logical_members(items, list(repaired.placements), baseline.relations)
    baseline.outcome.placements = expanded
    selected_ids = {value.container_id for value in expanded}
    priority = 1.0 + sum(value.cost for value in containers)
    used_cost = sum(value.cost for value in containers if value.container_id in selected_ids)
    baseline.outcome.solve.objective_value = float(len(selected_ids) * priority + used_cost)
    baseline.outcome.metadata.update({
        **metadata,
        "delivery_repair_phase": "local_repair_valid",
        "delivery_outcome_class": "VALID_WITH_ONE_EXTRA_CONTAINER" if repaired.opened_extra_container else "VALID_FIXED_CONTAINER",
    })
    return baseline


def _optional_int(settings: dict[str, Any], key: str) -> int | None:
    value = settings.get(key)
    return None if value is None else int(value)


def _mark_construction_time_limit(baseline, pipeline_limit: float, elapsed_seconds: float) -> None:
    """Return a non-solution when construction consumes the shared Level 8 budget."""
    baseline.outcome.solve = SolveResult(
        "TIME_LIMIT",
        "Level 8 construction exceeded the shared delivery pipeline time limit; repair was not started.",
        None,
        baseline.outcome.solve.vector,
        baseline.outcome.solve.raw_result,
    )
    baseline.outcome.placements = []
    baseline.outcome.metadata.update({
        "construction_time_limit_reached": True,
        "delivery_pipeline_deadline_reached": True,
        "delivery_pipeline_time_limit_seconds": pipeline_limit,
        "delivery_baseline_runtime_seconds": elapsed_seconds,
        "delivery_repair_phase": "skipped_construction_time_limit",
        "delivery_repair_candidates_evaluated": 0,
        "delivery_repair_termination_reason": "construction_time_limit",
        "delivery_outcome_class": "NO_VALID_LIFO_SOLUTION_WITHIN_BUDGET",
        "hide_objective_when_invalid": True,
    })


def _delivery_priority_settings(settings: dict[str, Any]) -> dict[str, Any]:
    # Exhaustive heterogeneous-container combinations become prohibitively
    # expensive once the sequential COG hard gate is active. Reuse the shared
    # bounded subset generator by lowering only its exhaustive-search
    # threshold for this delivery-first pass.
    use_sequential_balance = bool(
        settings.get("sequential_balance_construction_enabled", False)
    )
    result = {
        **settings,
        "sequential_balance_construction_enabled": use_sequential_balance,
        "compound_item_ordering": {
            "source_field": "delivery_priority",
            # Reverse loading order: later stops occupy the far side first,
            # leaving near-door positions for earlier deliveries.
            "direction": "descending",
        },
    }
    if use_sequential_balance:
        subset_threshold = int(
            settings.get("delivery_subset_enumeration_threshold", 4)
        )
        if subset_threshold <= 0:
            raise ValueError(
                "delivery_subset_enumeration_threshold must be positive"
            )
        result["subset_enumeration_limit"] = subset_threshold
    return result


def _construction_record(mode: str, result, items, rules, settings: dict[str, Any]) -> dict[str, object]:
    if result.outcome.solve.status != "FEASIBLE" or result.validation is None or not result.validation.result.valid:
        return {"mode": mode, "inherited_valid": False, "lifo_valid": False, "direct_rehandles": None}
    unloading = validate_unloading_lifo(
        items, list(result.placements), rules,
        tolerance_mm=float(settings.get("coordinate_tolerance_mm", 1e-6)),
    )
    return {
        "mode": mode,
        "inherited_valid": True,
        "lifo_valid": unloading.result.valid,
        "direct_rehandles": sum(value.minimum_rehandle_count for value in unloading.records),
        "used_container_count": len({value.container_id for value in result.placements}),
    }


def _construction_rank(result, items, rules, settings: dict[str, Any]) -> tuple[float, ...]:
    record = _construction_record("rank", result, items, rules, settings)
    if not record["inherited_valid"]:
        return (float("inf"),) * 4
    return (
        0.0 if record["lifo_valid"] else 1.0,
        float(record["direct_rehandles"] or 0),
        float(record["used_container_count"] or 0),
        float(result.outcome.solve.objective_value or 0.0),
    )


def _validate_solution(items, containers, placements, config):
    inherited = validate_level_07_fixture_bundle(items, containers, placements, config, None)
    unloading = validate_unloading_lifo(
        items, placements, unloading_rules(config),
        tolerance_mm=float(config.get("validation", {}).get("coordinate_tolerance_mm", 1e-6)),
    )
    static_bundle = compose_level_08_validation(inherited, unloading, items)
    return compose_optional_sequential_validation(
        static_bundle, list(items), list(containers), list(placements), config
    )


STRATEGY = LevelRuntimeStrategy(
    level_number=8,
    execute=_execute,
    validate_instance=_validate_delivery_instance,
    validate_solution=_validate_solution,
    guard_config=_guard,
    active_constraints=(
        "compound_boundaries", "compound_payload", "compound_non_overlap", "exact_base_support",
        "base_center_support", "stackability_same_group", "maximum_stack_layers",
        "recursive_static_load_transfer", "maximum_supported_weight",
        "compound_root_center_of_mass_balance", "static_lifo_no_later_priority_blockers",
    ),
    inactive_constraints=(
        "vertical_axis_rotation", "internal_nesting_load_transfer", "pressure", "contact_moments",
        "dynamic_load", "full_physical_stability", "axle_load_limits", "floor_zone_load_limits",
        "door_opening_geometry", "exact_removal_sequence", "handling_equipment", "temporary_staging_space",
    ),
    metadata_defaults={
        "experimental_runtime": True,
        "runtime_promotion_status": "cli_only_delivery_runtime_not_default",
        "delivery_final_validation_required": True,
        "hide_objective_when_invalid": True,
    },
    algorithm_roles={
        BEST_FIT_ALGORITHM_ID: "experimental_delivery_aware_practical_candidate",
        FFD_ALGORITHM_ID: "experimental_delivery_aware_fast_comparator",
    },
    post_write_hook=write_optional_sequential_artifacts,
    prevalidation_metadata_hook=sequential_prevalidation_metadata,
)


def run_from_config(
    config_path: str | Path, *, item_count: int | None = None, container_count: int | None = None,
    level_id: str = "level_08", algorithm_id: str = BEST_FIT_ALGORITHM_ID,
    environment: str = "local", random_seed: int | None = None,
    algorithm_parameters: dict[str, Any] | None = None, config_overrides: dict[str, Any] | None = None,
    item_selection_strategy: str | None = None, item_selection_seed: int | None = None,
):
    overrides = dict(config_overrides or {})
    overrides["project"] = {**dict(overrides.get("project", {})), "algorithm_id": algorithm_id}
    return run_configured_level(
        config_path, strategy=STRATEGY, item_count=item_count, container_count=container_count,
        level_id=level_id, algorithm_id=algorithm_id, environment=environment,
        random_seed=random_seed, algorithm_parameters=algorithm_parameters,
        config_overrides=overrides, item_selection_strategy=item_selection_strategy,
        item_selection_seed=item_selection_seed,
    )
