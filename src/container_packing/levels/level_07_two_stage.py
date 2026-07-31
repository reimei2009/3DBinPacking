"""Level 7 compact baseline followed by bounded local COG repair."""

from __future__ import annotations

from time import perf_counter
from typing import Callable

from ..algorithms.contracts import AlgorithmOutcome
from ..schemas import Container, Item, Placement
from .level_06_compound_adapter import (
    Level06CompoundAdapter,
    Level06CompoundResult,
    _expand_logical_members,
)
from .level_06_pipeline import validate_level_06_bundle
from .level_06_compound_policy import build_level_06_compound_fixture_policy
from .level_07_balance_repair import (
    BalanceRepairEngine,
    BalanceRepairStats,
    BalanceMomentCache,
    RootMassProperties,
    _allows_group,
    _dimensions,
    _ranking,
    _shift,
    _state,
    support_closures,
)
from .level_07_balance_lns import BalanceLnsEngine
from .level_07_balance_points import BalanceAnchorPointProvider
from .level_07_fixture_bundle import balance_rules, validate_level_07_fixture_bundle
from .nesting import attributes_for_item
from .nesting_runtime import (
    NestingCompoundProjection,
    compound_to_external_item,
    compound_to_external_placement,
    project_nesting_compounds,
)


CompoundSolver = Callable[..., AlgorithmOutcome]


def solve_two_stage_balance(
    items: list[Item], containers: list[Container], config: dict,
    *, algorithm_id: str, baseline_solver: CompoundSolver,
    additional_candidate_validator: Callable[[list[Placement]], bool] | None = None,
) -> Level06CompoundResult:
    """Minimize containers first, then repair balance without full rebuilds."""
    pipeline_started = perf_counter()
    baseline_started = perf_counter()
    baseline = Level06CompoundAdapter(
        algorithm_id, "level_07_stage1_level_06_compact_baseline_v1",
        baseline_solver, validate_level_07_fixture_bundle,
    ).solve(items, containers, config)
    baseline_seconds = perf_counter() - baseline_started
    pipeline_limit = max(
        0.0, float(config.get("balance_pipeline_time_limit_seconds", 45))
    )
    pipeline_deadline = pipeline_started + pipeline_limit
    remaining_pipeline_seconds = max(
        0.0, pipeline_limit - (perf_counter() - pipeline_started)
    )
    repair_limit = min(
        remaining_pipeline_seconds,
        max(0.0, float(config.get("balance_repair_time_limit_seconds", 45))),
    )
    local_limit = min(
        repair_limit,
        max(0.0, float(config.get("balance_repair_fixed_subset_seconds", 8))),
    )
    requested_extra_limit = max(
        0.0, float(config.get("balance_repair_extra_container_seconds", 5))
    )
    extra_limit = min(
        max(0.0, repair_limit - local_limit),
        requested_extra_limit,
    )
    # Reserve the configured rescue budget before giving the remainder to LNS.
    # Otherwise baseline runtime can consume part of the total pipeline budget
    # and silently reduce the extra-container phase to zero.
    lns_limit = min(
        max(0.0, repair_limit - local_limit - extra_limit),
        max(0.0, float(config.get("balance_repair_lns_seconds", 17))),
    )
    baseline.outcome.metadata.update({
        "balance_pipeline_time_limit_seconds": pipeline_limit,
        "balance_execution_mode": (
            "allow_one_extra_container"
            if int(config.get("balance_repair_max_extra_containers", 1)) > 0
            else "strict_fixed_container"
        ),
        "balance_repair_time_limit_seconds": repair_limit,
        "balance_repair_fixed_subset_seconds": local_limit,
        "balance_repair_lns_seconds": lns_limit,
        "balance_repair_extra_container_seconds": extra_limit,
        "balance_repair_max_candidates": int(
            config.get("balance_repair_max_candidates", 256)
        ),
        "balance_repair_contributor_limit": int(
            config.get("balance_repair_contributor_limit", 8)
        ),
        "balance_repair_max_extra_containers": int(
            config.get("balance_repair_max_extra_containers", 1)
        ),
    })
    if baseline.validation is not None and baseline.validation.result.valid:
        stats = BalanceRepairStats(termination_reason="baseline_already_valid")
        return _annotate(
            baseline, phase="baseline_valid", baseline_seconds=baseline_seconds,
            pipeline_started=pipeline_started, stats=stats,
            initial_count=_container_count(baseline.outcome.placements),
            final_count=_container_count(baseline.outcome.placements), opened=0,
        )
    if baseline.outcome.solve.status != "FEASIBLE" or baseline.projection is None:
        return _annotate(
            baseline, phase="baseline_incomplete", baseline_seconds=baseline_seconds,
            pipeline_started=pipeline_started, stats=BalanceRepairStats(),
            initial_count=0, final_count=0, opened=0,
        )

    original_by_id = {item.item_id: item for item in items}
    root_placements = [
        compound_to_external_placement(value) for value in baseline.projection.compounds
    ]
    root_items = [
        compound_to_external_item(value, original_by_id[value.root_item_id])
        for value in baseline.projection.compounds
    ]
    mass_properties = _compound_mass_properties(
        baseline.projection.compounds, original_by_id
    )
    used_ids = {value.container_id for value in root_placements}
    initial_container_count = len(used_ids)
    fixed = [value for value in containers if value.container_id in used_ids]
    remaining = sorted(
        (value for value in containers if value.container_id not in used_ids),
        key=lambda value: (value.cost, -value.volume_m3, value.container_id),
    )
    tolerance = float(config.get("coordinate_tolerance_mm", 1e-4))
    support = config["support"]
    engine = BalanceRepairEngine(
        policy=build_level_06_compound_fixture_policy(root_items, config),
        balance_config=balance_rules(config),
        coordinate_tolerance_mm=tolerance,
        support_epsilon_mm=float(support["epsilon_mm"]),
        max_candidates=int(config.get("balance_repair_max_candidates", 256)),
        contributor_limit=int(config.get("balance_repair_contributor_limit", 8)),
        mass_properties=mass_properties,
    )
    container_map = {value.container_id: value for value in containers}
    baseline_max_violation = _ranking(
        BalanceMomentCache.from_placements(root_placements, mass_properties),
        root_placements, container_map, balance_rules(config),
    )[0]
    phase_violations: dict[str, float] = {
        "balance_violation_baseline_max": baseline_max_violation,
        "balance_violation_after_local_max": baseline_max_violation,
        "balance_violation_after_lns_max": baseline_max_violation,
        "balance_violation_after_rescue_max": baseline_max_violation,
    }

    def validate_roots(candidate_roots: list[Placement]) -> bool:
        expanded, resolved = _expand_logical_members(
            items, candidate_roots, baseline.relations
        )
        valid = validate_level_07_fixture_bundle(
            items, containers, expanded, config, list(resolved)
        ).result.valid
        return valid and (
            additional_candidate_validator is None
            or additional_candidate_validator(expanded)
        )

    def validate_feasible_roots(candidate_roots: list[Placement]) -> bool:
        expanded, resolved = _expand_logical_members(
            items, candidate_roots, baseline.relations
        )
        valid = validate_level_06_bundle(
            items, containers, expanded, config, list(resolved)
        ).result.valid
        return valid and (
            additional_candidate_validator is None
            or additional_candidate_validator(expanded)
        )

    repair = engine.repair(
        root_items, fixed, root_placements,
        validate_candidate=validate_feasible_roots,
        validate_final_candidate=validate_roots,
        fixed_seconds=local_limit,
        extra_seconds=0,
        extra_containers=[],
    )
    phase_violations["balance_violation_after_local_max"] = (
        repair.stats.final_max_violation
    )
    lns_metadata: dict[str, object] = {}
    rescue_metadata: dict[str, object] = {
        "balance_rescue_attempted": False,
        "balance_rescue_candidates_evaluated": 0,
        "balance_rescue_accepted_moves": [],
        "balance_rescue_termination_reason": "not_attempted",
    }
    consolidation_metadata: dict[str, object] = {
        "balance_consolidation_attempted": False,
        "balance_consolidation_result": "not_applicable",
        "balance_consolidation_candidates_evaluated": 0,
    }
    search_roots = list(repair.best_feasible_placements)
    selected_roots = repair.placements
    phase = "repair_valid_local"
    opened = repair.opened_extra_containers
    if selected_roots is None and lns_limit > 0:
        lns = BalanceLnsEngine(
            policy=build_level_06_compound_fixture_policy(root_items, config),
            balance_config=balance_rules(config),
            coordinate_tolerance_mm=tolerance,
            support_epsilon_mm=float(support["epsilon_mm"]),
            max_candidates=int(config.get("balance_repair_lns_max_candidates", 256)),
            neighborhood_size=int(config.get("balance_repair_lns_neighborhood_size", 8)),
            affected_container_limit=int(config.get("balance_repair_lns_affected_container_limit", 3)),
            max_rounds=int(config.get("balance_repair_lns_max_rounds", 3)),
            mass_properties=mass_properties,
            neighborhood_sizes=tuple(
                int(value) for value in config.get(
                    "balance_repair_lns_neighborhood_sizes", [4, 8, 12]
                )
            ),
        ).repair(
            root_items, fixed, search_roots,
            validate_candidate=validate_feasible_roots,
            validate_final_candidate=validate_roots,
            time_limit_seconds=lns_limit,
        )
        lns_metadata = lns.stats.metadata()
        search_roots = list(lns.best_feasible_placements)
        phase_violations["balance_violation_after_lns_max"] = (
            lns.stats.final_max_violation
        )
        if lns.placements is not None:
            selected_roots = lns.placements
            phase = "repair_valid_lns"
            repair.stats.final_max_violation = 0.0
            repair.stats.termination_reason = "superseded_by_lns"
    else:
        phase_violations["balance_violation_after_lns_max"] = (
            repair.stats.final_max_violation
        )
    if selected_roots is None and extra_limit > 0 and remaining:
        extra_engine = BalanceRepairEngine(
            policy=build_level_06_compound_fixture_policy(root_items, config),
            balance_config=balance_rules(config),
            coordinate_tolerance_mm=tolerance,
            support_epsilon_mm=float(support["epsilon_mm"]),
            max_candidates=int(config.get("balance_repair_extra_max_candidates", 64)),
            contributor_limit=int(config.get("balance_repair_contributor_limit", 8)),
            mass_properties=mass_properties,
        )
        extra_repair = extra_engine.repair(
            root_items, fixed, search_roots,
            validate_candidate=validate_feasible_roots,
            validate_final_candidate=validate_roots, fixed_seconds=0,
            extra_seconds=extra_limit,
            extra_containers=remaining[:int(config.get("balance_repair_max_extra_containers", 1))],
        )
        rescue_metadata = {
            "balance_rescue_attempted": True,
            "balance_rescue_candidates_evaluated": (
                extra_repair.stats.candidates_evaluated
            ),
            "balance_rescue_improving_candidates_validated": (
                extra_repair.stats.improving_candidates_validated
            ),
            "balance_rescue_accepted_moves": list(
                extra_repair.stats.accepted_moves
            ),
            "balance_rescue_runtime_seconds": (
                extra_repair.stats.fixed_phase_seconds
                + extra_repair.stats.extra_phase_seconds
            ),
            "balance_rescue_termination_reason": (
                extra_repair.stats.termination_reason
            ),
            "balance_rescue_initial_max_violation": (
                extra_repair.stats.initial_max_violation
            ),
            "balance_rescue_final_max_violation": (
                extra_repair.stats.final_max_violation
            ),
        }
        search_roots = list(extra_repair.best_feasible_placements)
        phase_violations["balance_violation_after_rescue_max"] = (
            extra_repair.stats.final_max_violation
        )
        if extra_repair.placements is not None:
            selected_roots = extra_repair.placements
            repair = extra_repair
            opened = extra_repair.opened_extra_containers
            phase = "repair_valid_extra_container"
            if opened:
                consolidated, consolidation_metadata = _consolidate_extra_container(
                    root_items, [*fixed, remaining[0]], list(selected_roots),
                    extra_container_id=remaining[0].container_id,
                    policy=build_level_06_compound_fixture_policy(root_items, config),
                    config=config, mass_properties=mass_properties,
                    validate_candidate=validate_roots,
                    deadline=min(
                        pipeline_deadline,
                        perf_counter() + float(
                            config.get("balance_repair_consolidation_seconds", 2)
                        ),
                    ),
                )
                if consolidated is not None:
                    selected_roots = tuple(consolidated)
                    opened = 0
                    phase = "repair_valid_consolidated"
    else:
        phase_violations["balance_violation_after_rescue_max"] = (
            phase_violations["balance_violation_after_lns_max"]
        )
    if selected_roots is None:
        baseline.outcome.metadata.update({
            **lns_metadata,
            **rescue_metadata,
            **phase_violations,
            "balance_failure_reason": "NO_VALID_BALANCED_SOLUTION_WITHIN_BUDGET",
            "balance_outcome_class": "NO_VALID_BALANCED_SOLUTION_WITHIN_BUDGET",
        })
        return _annotate(
            baseline, phase="repair_budget_exhausted", baseline_seconds=baseline_seconds,
            pipeline_started=pipeline_started, stats=repair.stats,
            initial_count=initial_container_count,
            final_count=initial_container_count, opened=0,
        )

    roots = list(selected_roots)
    expanded, resolved = _expand_logical_members(items, roots, baseline.relations)
    validation = validate_level_07_fixture_bundle(
        items, containers, expanded, config, list(resolved)
    )
    attributes = {item.item_id: attributes_for_item(item) for item in items}
    projection = project_nesting_compounds(
        expanded, attributes, resolved,
        clearance_mm=float(config.get("nesting", {}).get("clearance_mm", 0.0)),
    )
    baseline.outcome.placements = expanded
    used_ids = {value.container_id for value in expanded}
    priority = 1.0 + sum(value.cost for value in containers)
    used_cost = sum(
        value.cost for value in containers if value.container_id in used_ids
    )
    baseline.outcome.solve.objective_value = float(
        len(used_ids) * priority + used_cost
    )
    baseline.outcome.solve.message = (
        "Level 6 compact baseline repaired locally to satisfy Level 7 COG balance."
    )
    result = Level06CompoundResult(
        baseline.outcome, len(items), baseline.construction, resolved,
        tuple(expanded), projection, validation,
    )
    result.outcome.metadata.update({
        **lns_metadata, **rescue_metadata, **consolidation_metadata,
        **phase_violations,
    })
    return _annotate(
        result, phase=phase, baseline_seconds=baseline_seconds,
        pipeline_started=pipeline_started, stats=repair.stats,
        initial_count=initial_container_count, final_count=_container_count(expanded),
        opened=opened,
    )


def _annotate(
    result: Level06CompoundResult, *, phase: str, baseline_seconds: float,
    pipeline_started: float, stats: BalanceRepairStats,
    initial_count: int, final_count: int, opened: int,
) -> Level06CompoundResult:
    total_seconds = perf_counter() - pipeline_started
    result.outcome.metadata.update({
        "balance_pipeline": "level_06_compact_then_local_cog_repair_v2",
        "balance_repair_phase": phase,
        "balance_repair_opened_extra_containers": opened,
        "balance_repair_initial_container_count": initial_count,
        "balance_repair_final_container_count": final_count,
        "balance_baseline_runtime_seconds": baseline_seconds,
        "balance_repair_runtime_seconds": max(0.0, total_seconds - baseline_seconds),
        "balance_pipeline_runtime_seconds": total_seconds,
        "hide_objective_when_invalid": True,
        "balance_outcome_class": (
            "VALID_WITH_ONE_EXTRA_CONTAINER"
            if phase == "repair_valid_extra_container"
            else "VALID_FIXED_CONTAINER"
            if phase in {
                "baseline_valid", "repair_valid_local", "repair_valid_lns",
                "repair_valid_consolidated",
            }
            else "NO_VALID_BALANCED_SOLUTION_WITHIN_BUDGET"
        ),
        **stats.metadata(),
    })
    return result


def _container_count(placements: list[Placement]) -> int:
    return len({value.container_id for value in placements})


def _compound_mass_properties(
    compounds: tuple[NestingCompoundProjection, ...], items: dict[str, Item]
) -> dict[str, RootMassProperties]:
    properties: dict[str, RootMassProperties] = {}
    for compound in compounds:
        members = [items[value] for value in compound.member_item_ids]
        mass = sum(value.weight_kg for value in members)
        if mass <= 0:
            raise ValueError(
                f"Compound {compound.root_item_id} has non-positive total mass"
            )
        properties[compound.root_item_id] = RootMassProperties(
            mass,
            sum(value.weight_kg * value.length_mm / 2.0 for value in members) / mass,
            sum(value.weight_kg * value.width_mm / 2.0 for value in members) / mass,
        )
    return properties


def _consolidate_extra_container(
    items: list[Item], containers: list[Container],
    placements: list[Placement], *, extra_container_id: str,
    policy, config: dict, mass_properties: dict[str, RootMassProperties],
    validate_candidate: Callable[[list[Placement]], bool], deadline: float,
) -> tuple[list[Placement] | None, dict[str, object]]:
    """Try to close the rescue container by moving complete support closures."""
    metadata: dict[str, object] = {
        "balance_consolidation_attempted": True,
        "balance_consolidation_result": "not_eliminated_within_budget",
        "balance_consolidation_candidates_evaluated": 0,
    }
    extra_ids = {
        value.item_id for value in placements
        if value.container_id == extra_container_id
    }
    if not extra_ids:
        metadata["balance_consolidation_result"] = "extra_container_already_empty"
        return placements, metadata
    epsilon = float(config["support"]["epsilon_mm"])
    closures = support_closures(placements, epsilon)
    roots = [
        item_id for item_id in sorted(extra_ids)
        if not any(
            item_id in closure and item_id != parent_id
            for parent_id, closure in closures.items()
            if parent_id in extra_ids
        )
    ]
    item_by_id = {value.item_id: value for value in items}
    fixed_containers = [
        value for value in containers if value.container_id != extra_container_id
    ]
    container_map = {value.container_id: value for value in containers}
    balance_config = balance_rules(config)
    anchors = BalanceAnchorPointProvider(balance_config)
    current = list(placements)
    tolerance = float(config.get("coordinate_tolerance_mm", 1e-4))
    for root_id in roots:
        if perf_counter() >= deadline:
            return None, metadata
        moving_ids = closures[root_id] & extra_ids
        moving = [value for value in current if value.item_id in moving_ids]
        remaining = [value for value in current if value.item_id not in moving_ids]
        root = next(value for value in moving if value.item_id == root_id)
        best: tuple[tuple[float, ...], list[Placement]] | None = None
        for target in fixed_containers:
            state = _state(target, remaining, tolerance)
            for point in anchors.points(
                state, item_by_id[root_id], _dimensions(root)
            )[:24]:
                if perf_counter() >= deadline:
                    return None, metadata
                delta = (
                    point[0] - root.x_mm,
                    point[1] - root.y_mm,
                    point[2] - root.z_mm,
                )
                added = [
                    _shift(value, target.container_id, delta)
                    for value in sorted(moving, key=lambda value: (value.z_mm, value.item_id))
                ]
                metadata["balance_consolidation_candidates_evaluated"] = int(
                    metadata["balance_consolidation_candidates_evaluated"]
                ) + 1
                if not _allows_group(state, added, policy, tolerance):
                    continue
                trial = [*remaining, *added]
                moments = BalanceMomentCache.from_placements(trial, mass_properties)
                score = _ranking(moments, trial, container_map, balance_config)
                if best is None or score < best[0]:
                    best = score, added
        if best is None:
            return None, metadata
        current = [*remaining, *best[1]]
    if any(value.container_id == extra_container_id for value in current):
        return None, metadata
    if not validate_candidate(current):
        metadata["balance_consolidation_result"] = "eliminated_but_final_validation_failed"
        return None, metadata
    metadata["balance_consolidation_result"] = "extra_container_eliminated"
    return current, metadata
