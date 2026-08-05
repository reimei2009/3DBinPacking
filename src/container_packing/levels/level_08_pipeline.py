"""Config-driven Level 8 constructive runtime over the inherited Level 7 stack."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any

from ..algorithms.heuristics.extreme_point_best_fit import solve as solve_best_fit
from ..algorithms.heuristics.extreme_point_ffd import solve as solve_ffd
from ..algorithms.heuristics.container_subset_selection import (
    AdaptiveContainerSubsetSelectionPolicy,
)
from ..algorithms.heuristics.container_assignment import (
    StopAwareBeamAssignmentPlanner,
)
from ..data_loader import load_config
from ..schemas import Placement, ValidationResult
from ..schemas import SolveResult
from .level_03_preprocessing import validate_instance
from .level_06_compound_adapter import _expand_logical_members
from .level_06_compound_policy import build_level_06_compound_fixture_policy
from .level_06_pipeline import _guard as guard_level_06
from .level_07_fixture_bundle import balance_rules, validate_level_07_fixture_bundle
from .level_07_two_stage import (
    _compound_mass_properties,
    _consolidate_extra_container,
    solve_two_stage_balance,
)
from .level_08_delivery_scoring import (
    DeliveryAwareCandidateScoringPolicy,
    DeliveryAwareFirstFitCandidateSelection,
    DeliveryDependencyFeasibilityPolicy,
    DeliveryDoorPointProvider,
    SequentialBalanceFeasibilityPolicy,
    StrictLifoFeasibilityPolicy,
)
from .level_08_validation import compose_level_08_validation, validate_unloading_lifo
from .level_08_delivery_repair import DeliveryRepairEngine
from .level_08_container_elimination import DeliveryContainerEliminationLns
from .level_08_sequential_runtime import (
    compose_optional_sequential_validation,
    sequential_prevalidation_metadata,
    sequential_runtime_options,
    write_optional_sequential_artifacts,
)
from .level_08_routing import (
    routing_options,
    write_optional_routing_artifacts,
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
    routing_options(config)


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
        def compact_solver(compounds, available, config, **kwargs):
            return solve_best_fit(
                compounds,
                available,
                config,
                container_subset_policy=_delivery_container_subset_policy(config),
                **kwargs,
            )

        def delivery_solver(compounds, available, config, **kwargs):
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
            policy = DeliveryDependencyFeasibilityPolicy(
                {item.item_id: item for item in compounds},
                policy,
                support_epsilon_mm=float(config["support"]["epsilon_mm"]),
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
                container_subset_policy=_delivery_container_subset_policy(config),
                **kwargs,
            )

        def stop_assignment_solver(compounds, available, config, **kwargs):
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
            policy = DeliveryDependencyFeasibilityPolicy(
                {item.item_id: item for item in compounds},
                policy,
                support_epsilon_mm=float(config["support"]["epsilon_mm"]),
            )
            if balance_config is not None:
                policy = SequentialBalanceFeasibilityPolicy(
                    balance_config, policy
                )
            assignment = _stop_assignment_options(config)
            return solve_best_fit(
                compounds,
                available,
                config,
                policy=policy,
                candidate_scoring_policy=DeliveryAwareCandidateScoringPolicy(
                    {item.item_id: item for item in compounds},
                    unloading,
                    balance_config,
                ),
                candidate_point_provider=DeliveryDoorPointProvider(
                    unloading, balance_config
                ),
                container_subset_policy=_delivery_container_subset_policy(config),
                container_assignment_planner=StopAwareBeamAssignmentPlanner(
                    beam_width=int(assignment["beam_width"]),
                    max_plans_per_subset=int(
                        assignment["max_plans_per_subset"]
                    ),
                    utilization_target=float(
                        assignment["utilization_target"]
                    ),
                ),
                **kwargs,
            )
    elif algorithm_id == FFD_ALGORITHM_ID:
        stop_assignment_solver = None
        def compact_solver(compounds, available, config, **kwargs):
            return solve_ffd(
                compounds,
                available,
                config,
                container_subset_policy=_delivery_container_subset_policy(config),
                **kwargs,
            )

        def delivery_solver(compounds, available, config, **kwargs):
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
            policy = DeliveryDependencyFeasibilityPolicy(
                {item.item_id: item for item in compounds},
                policy,
                support_epsilon_mm=float(config["support"]["epsilon_mm"]),
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
                container_subset_policy=_delivery_container_subset_policy(config),
                **kwargs,
            )
    else:
        raise ValueError(f"Unsupported Level 8 algorithm: {algorithm_id}")
    def construct_balance_valid(
        source_settings: dict[str, Any], baseline_solver,
    ):
        """Build the compact delivery candidate, then apply Level 7 repair.

        Level 8 may only enter static LIFO and sequential replay from a
        balance-valid Level 1--7 state.  Reusing the canonical two-stage
        engine avoids treating the Level 7 validator as a passive final gate.
        """
        candidate_deadline = pipeline_deadline
        requested_deadline = source_settings.get(
            "constructive_deadline_monotonic"
        )
        if requested_deadline is not None:
            candidate_deadline = min(
                candidate_deadline, float(requested_deadline)
            )
        remaining = max(0.0, candidate_deadline - perf_counter())
        return solve_two_stage_balance(
            items,
            containers,
            {
                **source_settings,
                "balance_pipeline_time_limit_seconds": remaining,
                "balance_repair_time_limit_seconds": remaining,
            },
            algorithm_id=algorithm_id,
            baseline_solver=baseline_solver,
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
    delivery_fallback = None
    stop_assignment_candidate = None
    if construction_mode == "delivery_priority_primary":
        baseline = construct_balance_valid(delivery_settings, delivery_solver)
        construction_records.append(_construction_record("delivery_priority_primary", baseline, items, rules, settings))
    else:
        baseline = construct_balance_valid(compact_settings, compact_solver)
        construction_records.append(_construction_record("compact_baseline", baseline, items, rules, settings))
        if (
            len(items) <= compare_max_items
            and baseline.outcome.solve.status == "FEASIBLE"
            and baseline.validation is not None
            and baseline.validation.result.valid
            and not validate_unloading_lifo(items, list(baseline.placements), rules).result.valid
        ):
            delivery_candidate = construct_balance_valid(
                delivery_settings, delivery_solver
            )
            construction_records.append(_construction_record("delivery_priority_compare", delivery_candidate, items, rules, settings))
            delivery_fallback = delivery_candidate
    assignment_options = _stop_assignment_options(settings)
    assignment_skip_reason = "disabled"
    if (
        algorithm_id == BEST_FIT_ALGORITHM_ID
        and bool(assignment_options["enabled"])
        and len(items) <= int(assignment_options["max_items"])
        and perf_counter() < pipeline_deadline
        and stop_assignment_solver is not None
    ):
        assignment_started = perf_counter()
        assignment_deadline = min(
            pipeline_deadline,
            assignment_started
            + max(0.0, float(assignment_options["time_limit_seconds"])),
        )
        assignment_settings = {
            **delivery_settings,
            "constructive_deadline_monotonic": assignment_deadline,
        }
        stop_assignment_candidate = construct_balance_valid(
            assignment_settings, stop_assignment_solver
        )
        stop_assignment_candidate.outcome.metadata.update({
            "delivery_stop_assignment_candidate": True,
            "delivery_stop_assignment_runtime_seconds": (
                perf_counter() - assignment_started
            ),
        })
        construction_records.append(_construction_record(
            "stop_aware_fixed_subset",
            stop_assignment_candidate,
            items,
            rules,
            settings,
        ))
        assignment_skip_reason = "candidate_evaluated"
    elif algorithm_id != BEST_FIT_ALGORITHM_ID:
        assignment_skip_reason = "best_fit_only"
    elif len(items) > int(assignment_options["max_items"]):
        assignment_skip_reason = "item_limit"
    elif perf_counter() >= pipeline_deadline:
        assignment_skip_reason = "no_pipeline_budget"
    baseline_seconds = perf_counter() - pipeline_started
    remaining_seconds = max(0.0, pipeline_limit - baseline_seconds)
    pipeline_metadata = {
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
        "delivery_stop_assignment_enabled": bool(assignment_options["enabled"]),
        "delivery_stop_assignment_skip_reason": assignment_skip_reason,
        "delivery_stop_assignment_beam_width": int(assignment_options["beam_width"]),
        "delivery_stop_assignment_max_plans_per_subset": int(
            assignment_options["max_plans_per_subset"]
        ),
        "delivery_stop_assignment_utilization_target": float(
            assignment_options["utilization_target"]
        ),
        "delivery_stop_assignment_time_limit_seconds": float(
            assignment_options["time_limit_seconds"]
        ),
    }
    baseline.outcome.metadata.update(pipeline_metadata)
    if delivery_fallback is not None:
        delivery_fallback.outcome.metadata.update(pipeline_metadata)
    if stop_assignment_candidate is not None:
        stop_assignment_candidate.outcome.metadata.update(pipeline_metadata)
    additional_candidates = [
        value for value in (delivery_fallback, stop_assignment_candidate)
        if value is not None
    ]
    if baseline.outcome.solve.status == "TIME_LIMIT":
        _mark_construction_time_limit(baseline, pipeline_limit, baseline_seconds)
        return baseline.outcome
    if baseline.outcome.solve.status != "FEASIBLE" or baseline.validation is None or not baseline.validation.result.valid:
        if additional_candidates:
            return _select_final_construction_candidate(
                [baseline, *additional_candidates], items, containers, settings,
                pipeline_deadline=pipeline_deadline,
                pipeline_started=pipeline_started,
            ).outcome
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
        return _select_final_construction_candidate(
            [
                baseline,
                *additional_candidates,
            ],
            items,
            containers,
            settings,
            pipeline_deadline=pipeline_deadline,
            pipeline_started=pipeline_started,
        ).outcome
    repaired = _repair_delivery_order(
        items, containers, settings, rules, baseline,
        repair_seconds=remaining_seconds, pipeline_started=pipeline_started,
    )
    return _select_final_construction_candidate(
        [
            repaired,
            *additional_candidates,
        ],
        items,
        containers,
        settings,
        pipeline_deadline=pipeline_deadline,
        pipeline_started=pipeline_started,
    ).outcome


def _select_final_construction_candidate(
    candidates, items, containers, settings: dict[str, Any], *,
    pipeline_deadline: float | None = None,
    pipeline_started: float | None = None,
):
    """Select only after evaluating the complete Level 1--8 contract.

    Compact construction remains the first repair target. The delivery-first
    construction is a deterministic fallback, not an automatic replacement
    merely because it is static-LIFO valid with more containers.
    """
    unique = []
    seen: set[tuple[tuple[str, str, float, float, float], ...]] = set()
    for candidate in candidates:
        signature = tuple(sorted(
            (
                value.item_id, value.container_id,
                value.x_mm, value.y_mm, value.z_mm,
            )
            for value in candidate.outcome.placements
        ))
        if signature not in seen:
            seen.add(signature)
            unique.append(candidate)

    ranked = []
    candidate_records: list[dict[str, object]] = []
    for candidate in unique:
        final_valid = False
        if (
            candidate.outcome.solve.status == "FEASIBLE"
            and candidate.outcome.placements
        ):
            final_valid = _validate_solution(
                items,
                containers,
                list(candidate.outcome.placements),
                settings,
            ).result.valid
        used_ids = {
            value.container_id for value in candidate.outcome.placements
        }
        used_cost = sum(
            value.cost for value in containers
            if value.container_id in used_ids
        )
        ranked.append((
            (
                0 if final_valid else 1,
                len(used_ids) if used_ids else 10**9,
                used_cost,
            ),
            candidate,
            final_valid,
        ))
        candidate_records.append({
            "construction_mode": (
                "stop_aware_fixed_subset"
                if candidate.outcome.metadata.get(
                    "delivery_stop_assignment_candidate"
                )
                else "delivery_priority"
                if candidate.outcome.metadata.get(
                    "compound_item_ordering_source_field"
                ) == "delivery_priority"
                else "compact"
            ),
            "final_valid": final_valid,
            "container_count": len(used_ids),
            "total_cost": used_cost,
            "static_direct_rehandles": candidate.outcome.metadata.get(
                "total_direct_rehandles"
            ),
            "repair_phase": candidate.outcome.metadata.get(
                "delivery_repair_phase"
            ),
            "repair_termination_reason": candidate.outcome.metadata.get(
                "delivery_repair_termination_reason"
            ),
            "repair_candidates_evaluated": candidate.outcome.metadata.get(
                "delivery_repair_candidates_evaluated"
            ),
        })
    _, selected, final_valid = min(ranked, key=lambda value: value[0])
    if final_valid:
        _consolidate_selected_candidate(
            selected,
            items,
            containers,
            settings,
            pipeline_deadline=pipeline_deadline,
        )
        final_valid = _validate_solution(
            items, containers, list(selected.outcome.placements), settings
        ).result.valid
    requested_mode = str(
        selected.outcome.metadata.get(
            "delivery_construction_mode_requested", "compact_then_delivery_priority"
        )
    )
    delivery_ordered = (
        selected.outcome.metadata.get("compound_item_ordering_source_field")
        == "delivery_priority"
    )
    selected_mode = (
        "stop_aware_fixed_subset"
        if selected.outcome.metadata.get("delivery_stop_assignment_candidate")
        else (
            "delivery_priority_primary"
            if requested_mode == "delivery_priority_primary"
            else "delivery_priority_compare"
        )
        if delivery_ordered
        else "compact_baseline"
    )
    selected.outcome.metadata.update({
        "delivery_final_candidate_selection": "full_level_01_08_validation_then_container_count_cost_v1",
        "delivery_final_candidates_evaluated": len(ranked),
        "delivery_final_candidate_valid": final_valid,
        "delivery_final_candidate_records": candidate_records,
        "delivery_construction_mode_selected": selected_mode,
    })
    if pipeline_started is not None:
        selected.outcome.metadata["algorithm_runtime_seconds"] = (
            perf_counter() - pipeline_started
        )
    return selected


def _consolidate_selected_candidate(
    selected, items, containers, settings: dict[str, Any], *,
    pipeline_deadline: float | None,
) -> None:
    """Greedily eliminate lightly loaded containers without weakening Level 1--8.

    The search moves complete support closures, never individual nested/support
    members.  It only targets containers already used by the selected valid
    solution.  Consequently a failed elimination cannot silently exchange one
    container for another or increase the primary objective.
    """
    enabled = bool(settings.get("delivery_container_elimination_enabled", True))
    budget_seconds = max(
        0.0,
        float(settings.get("delivery_container_elimination_time_limit_seconds", 5.0)),
    )
    metadata: dict[str, object] = {
        "delivery_container_elimination_enabled": enabled,
        "delivery_container_elimination_attempted": False,
        "delivery_container_elimination_initial_count": len({
            value.container_id for value in selected.outcome.placements
        }),
        "delivery_container_elimination_final_count": len({
            value.container_id for value in selected.outcome.placements
        }),
        "delivery_container_elimination_attempts": 0,
        "delivery_container_elimination_successes": 0,
        "delivery_container_elimination_candidates_evaluated": 0,
        "delivery_container_elimination_lns_enabled": bool(
            settings.get("delivery_container_elimination_lns_enabled", True)
        ),
        "delivery_container_elimination_lns_attempts": 0,
        "delivery_container_elimination_lns_neighborhoods": 0,
        "delivery_container_elimination_lns_candidates_evaluated": 0,
        "delivery_container_elimination_lns_selected_neighborhood_size": None,
        "delivery_container_elimination_lns_termination_reason": "not_started",
        "delivery_container_elimination_termination_reason": "disabled",
        "delivery_container_elimination_closed_ids": [],
    }
    selected.outcome.metadata.update(metadata)
    if not enabled or budget_seconds <= 0 or selected.projection is None:
        return

    started = perf_counter()
    deadline = started + budget_seconds
    if pipeline_deadline is not None:
        deadline = min(deadline, pipeline_deadline)
    if perf_counter() >= deadline:
        selected.outcome.metadata.update({
            "delivery_container_elimination_termination_reason": "no_pipeline_budget",
            "delivery_container_elimination_runtime_seconds": 0.0,
        })
        return

    original_by_id = {value.item_id: value for value in items}
    root_items = [
        compound_to_external_item(value, original_by_id[value.root_item_id])
        for value in selected.projection.compounds
    ]
    logical_by_id = {value.item_id: value for value in selected.outcome.placements}
    roots = []
    for compound in selected.projection.compounds:
        logical = logical_by_id[compound.root_item_id]
        external = compound_to_external_placement(compound)
        roots.append(Placement(
            external.item_id,
            logical.container_id,
            logical.x_mm,
            logical.y_mm,
            logical.z_mm,
            external.length_mm,
            external.width_mm,
            external.height_mm,
            external.weight_kg,
            external.orientation_code,
        ))
    mass_properties = _compound_mass_properties(
        selected.projection.compounds, original_by_id
    )
    policy = build_level_06_compound_fixture_policy(root_items, settings)
    used_container_ids = {value.container_id for value in roots}
    container_by_id = {value.container_id: value for value in containers}
    closed_ids: list[str] = []
    attempts = successes = candidates_evaluated = 0
    lns_attempts = lns_neighborhoods = lns_candidates = 0
    lns_selected_size: int | None = None
    lns_termination_reason = "not_started"

    def validate_candidate(candidate_roots):
        expanded, _ = _expand_logical_members(
            items, candidate_roots, selected.relations
        )
        return _validate_solution(
            items, containers, expanded, settings
        ).result.valid

    while len(used_container_ids) > 1 and perf_counter() < deadline:
        loads = {
            container_id: (
                sum(1 for value in roots if value.container_id == container_id),
                sum(
                    value.length_mm * value.width_mm * value.height_mm
                    for value in roots if value.container_id == container_id
                ),
                -container_by_id[container_id].cost,
                container_id,
            )
            for container_id in used_container_ids
        }
        eliminated = False
        for donor_id in sorted(used_container_ids, key=lambda value: loads[value]):
            if perf_counter() >= deadline:
                break
            attempts += 1
            active_containers = [
                container_by_id[value] for value in sorted(used_container_ids)
            ]
            consolidated, evidence = _consolidate_extra_container(
                root_items,
                active_containers,
                roots,
                extra_container_id=donor_id,
                policy=policy,
                config=settings,
                mass_properties=mass_properties,
                validate_candidate=validate_candidate,
                deadline=deadline,
            )
            candidates_evaluated += int(
                evidence.get("balance_consolidation_candidates_evaluated", 0)
            )
            if consolidated is None:
                continue
            roots = consolidated
            used_container_ids.remove(donor_id)
            closed_ids.append(donor_id)
            successes += 1
            eliminated = True
            break
        if not eliminated:
            if not bool(
                settings.get("delivery_container_elimination_lns_enabled", True)
            ):
                break
            unloading_settings = UnloadingSettings.from_config(
                unloading_rules(settings)
            )
            lns_policy = StrictLifoFeasibilityPolicy(
                {value.item_id: value for value in root_items},
                unloading_settings,
                build_level_06_compound_fixture_policy(root_items, settings),
            )
            lns_policy = DeliveryDependencyFeasibilityPolicy(
                {value.item_id: value for value in root_items},
                lns_policy,
                support_epsilon_mm=float(settings["support"]["epsilon_mm"]),
            )
            lns = DeliveryContainerEliminationLns(
                policy=lns_policy,
                unloading_settings=unloading_settings,
                balance_config=balance_rules(settings),
                tolerance_mm=float(
                    settings.get("coordinate_tolerance_mm", 1e-6)
                ),
                support_epsilon_mm=float(settings["support"]["epsilon_mm"]),
                neighborhood_sizes=tuple(
                    int(value) for value in settings.get(
                        "delivery_container_elimination_lns_neighborhood_sizes",
                        [4, 8, 12],
                    )
                ),
                max_candidates=int(settings.get(
                    "delivery_container_elimination_lns_max_candidates", 2048
                )),
                points_per_group=int(settings.get(
                    "delivery_container_elimination_lns_points_per_group", 24
                )),
            )
            result = lns.eliminate(
                root_items,
                [container_by_id[value] for value in sorted(used_container_ids)],
                roots,
                donor_ids=sorted(used_container_ids, key=lambda value: loads[value]),
                validate_final=validate_candidate,
                deadline=deadline,
            )
            lns_attempts += result.attempts
            lns_neighborhoods += result.neighborhoods_evaluated
            lns_candidates += result.candidates_evaluated
            lns_selected_size = result.selected_neighborhood_size
            lns_termination_reason = result.termination_reason
            if result.placements is None:
                break
            previous_ids = set(used_container_ids)
            roots = list(result.placements)
            used_container_ids = {value.container_id for value in roots}
            newly_closed = sorted(previous_ids - used_container_ids)
            closed_ids.extend(newly_closed)
            successes += len(newly_closed)
            if not newly_closed:
                break

    if successes:
        expanded, _ = _expand_logical_members(items, roots, selected.relations)
        if _validate_solution(items, containers, expanded, settings).result.valid:
            selected.outcome.placements = expanded
            priority = 1.0 + sum(value.cost for value in containers)
            used_cost = sum(
                value.cost for value in containers
                if value.container_id in used_container_ids
            )
            selected.outcome.solve.objective_value = float(
                len(used_container_ids) * priority + used_cost
            )

    selected.outcome.metadata.update({
        "delivery_container_elimination_attempted": attempts > 0,
        "delivery_container_elimination_attempts": attempts,
        "delivery_container_elimination_successes": successes,
        "delivery_container_elimination_candidates_evaluated": candidates_evaluated,
        "delivery_container_elimination_lns_attempts": lns_attempts,
        "delivery_container_elimination_lns_neighborhoods": lns_neighborhoods,
        "delivery_container_elimination_lns_candidates_evaluated": lns_candidates,
        "delivery_container_elimination_lns_selected_neighborhood_size": lns_selected_size,
        "delivery_container_elimination_lns_termination_reason": lns_termination_reason,
        "delivery_container_elimination_final_count": len(used_container_ids),
        "delivery_container_elimination_closed_ids": closed_ids,
        "delivery_container_elimination_runtime_seconds": perf_counter() - started,
        "delivery_container_elimination_termination_reason": (
            "container_eliminated"
            if successes
            else "time_limit"
            if perf_counter() >= deadline
            else "lns_candidate_limit"
            if lns_termination_reason == "candidate_limit"
            else "no_valid_elimination"
        ),
    })


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


def _stop_assignment_options(settings: dict[str, Any]) -> dict[str, object]:
    raw = settings.get("delivery_stop_assignment", {})
    if not isinstance(raw, dict):
        raise ValueError("delivery_stop_assignment must be a mapping")
    result: dict[str, object] = {
        "enabled": bool(raw.get("enabled", True)),
        "beam_width": int(raw.get("beam_width", 32)),
        "max_plans_per_subset": int(raw.get("max_plans_per_subset", 16)),
        "utilization_target": float(raw.get("utilization_target", 0.85)),
        "time_limit_seconds": float(raw.get("time_limit_seconds", 10)),
        "max_items": int(raw.get("max_items", 300)),
    }
    if (
        int(result["beam_width"]) <= 0
        or int(result["max_plans_per_subset"]) <= 0
        or int(result["max_items"]) <= 0
        or float(result["time_limit_seconds"]) < 0
    ):
        raise ValueError("Level 8 stop-assignment budgets are invalid")
    if not 0 < float(result["utilization_target"]) <= 1:
        raise ValueError(
            "delivery_stop_assignment.utilization_target must be in (0, 1]"
        )
    return result


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
            "within_group_order": str(
                settings.get("delivery_within_stop_order", "decreasing_volume")
            ),
        },
    }
    return result


def _delivery_container_subset_policy(
    settings: dict[str, Any],
) -> AdaptiveContainerSubsetSelectionPolicy:
    """Resolve Level 8's exact-small / bounded-large subset policy.

    Levels 1--7 retain the legacy subset generator because the policy is only
    injected by this Level 8 adapter.
    """
    return AdaptiveContainerSubsetSelectionPolicy(
        exhaustive_max_containers=int(
            settings.get("delivery_subset_exhaustive_max_containers", 8)
        ),
        max_candidates_per_count=int(
            settings.get("delivery_subset_max_candidates_per_count", 32)
        ),
    )


def _construction_record(mode: str, result, items, rules, settings: dict[str, Any]) -> dict[str, object]:
    assignment_metadata = result.outcome.metadata
    solver_status = result.outcome.solve.status
    inherited_valid = bool(
        solver_status == "FEASIBLE"
        and result.validation is not None
        and result.validation.result.valid
    )
    failure_stage = (
        "none"
        if inherited_valid
        else "affinity_planning"
        if assignment_metadata.get("container_assignment_plans_generated") == 0
        else "construction"
        if solver_status in {"INFEASIBLE_HEURISTIC", "TIME_LIMIT"}
        else "inherited_validation"
    )
    assignment_evidence = {
        "assignment_mode": assignment_metadata.get("container_assignment_mode"),
        "assignment_plans_evaluated": assignment_metadata.get(
            "container_assignment_plans_evaluated"
        ),
        "assignment_planned_container_count": assignment_metadata.get(
            "container_assignment_planned_used_count"
        ),
        "assignment_actual_container_count": assignment_metadata.get(
            "container_assignment_actual_used_count"
        ),
        "assignment_planned_stop_fragmentation": assignment_metadata.get(
            "container_assignment_planned_stop_fragmentation"
        ),
        "assignment_actual_stop_fragmentation": assignment_metadata.get(
            "container_assignment_actual_stop_fragmentation"
        ),
        "assignment_preferred_hits": assignment_metadata.get(
            "container_affinity_preferred_hits"
        ),
        "assignment_fallback_count": assignment_metadata.get(
            "container_affinity_fallback_count"
        ),
        "assignment_groups_moved": assignment_metadata.get(
            "container_affinity_groups_moved_from_first_preference"
        ),
        "assignment_termination_reason": assignment_metadata.get(
            "container_assignment_termination_reason"
        ),
        "assignment_failure_stage": failure_stage,
        "assignment_runtime_seconds": assignment_metadata.get(
            "delivery_stop_assignment_runtime_seconds"
        ),
    }
    if not inherited_valid:
        return {
            "mode": mode,
            "solver_status": result.outcome.solve.status,
            "inherited_valid": False,
            "lifo_valid": False,
            "direct_rehandles": None,
            "candidate_subset_ids": result.outcome.metadata.get("candidate_container_ids", []),
            "subset_search_mode": result.outcome.metadata.get("container_subset_search_mode"),
            **assignment_evidence,
        }
    unloading = validate_unloading_lifo(
        items, list(result.placements), rules,
        tolerance_mm=float(settings.get("coordinate_tolerance_mm", 1e-6)),
    )
    return {
        "mode": mode,
        "solver_status": result.outcome.solve.status,
        "inherited_valid": True,
        "lifo_valid": unloading.result.valid,
        "direct_rehandles": sum(value.minimum_rehandle_count for value in unloading.records),
        "used_container_count": len({value.container_id for value in result.placements}),
        "candidate_subset_ids": result.outcome.metadata.get("candidate_container_ids", []),
        "subset_search_mode": result.outcome.metadata.get("container_subset_search_mode"),
        **assignment_evidence,
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


def _write_level_08_postprocessing(
    run_dir,
    items,
    containers,
    placements,
    config,
    metadata,
    bundle,
) -> None:
    """Persist replay first, then optional route enrichment."""
    write_optional_sequential_artifacts(
        run_dir, items, containers, placements, config, metadata, bundle
    )
    write_optional_routing_artifacts(run_dir, items, config, metadata, bundle)


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
    post_write_hook=_write_level_08_postprocessing,
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
