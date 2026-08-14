"""Điều phối bounded inventory search độc lập với constraint từng level."""

from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Any, Protocol

from scipy.optimize import OptimizeResult

from ..contracts import AlgorithmOutcome, SearchBudget
from ..orientation import OrientationProvider
from ...schemas import Container, Item, Placement, SolveResult
from .configuration import ContainerSearchConfiguration
from .inventory import NormalizedContainerInventory, normalize_container_inventory
from .inventory_consolidation import (
    BoundedInventoryConsolidator,
    SupportClosureProvider,
    inventory_item_order,
)
from .incumbent import CandidateValidator, ValidatedIncumbentStore
from .secondary_score import calculate_secondary_search_score
from .precheck import (
    assess_capacity_within_container_limit,
    estimate_container_lower_bound,
    run_hard_precheck,
)
from .subset_generation import (
    LazyRankedContainerSubsetPolicy,
    midpoint_cardinality_ladder,
)


class InventoryConstructiveExecutor(Protocol):
    """Constructive solver nhận policy subset do inventory orchestration tạo."""

    def __call__(
        self,
        items: list[Item],
        containers: list[Container],
        settings: dict[str, Any],
        *,
        container_subset_policy: LazyRankedContainerSubsetPolicy,
    ) -> AlgorithmOutcome:
        ...


@dataclass(frozen=True)
class InventorySearchRequest:
    """Input tối thiểu để chạy inventory search cho một level cụ thể."""

    algorithm_id: str
    items: list[Item]
    containers: list[Container]
    settings: dict[str, Any]
    configuration: ContainerSearchConfiguration
    supported_algorithm_ids: frozenset[str]
    orientation_provider: OrientationProvider
    precheck_backend: str = "inventory-aware-precheck"
    precheck_failure_context: str = "inventory instance"
    support_closure_provider: SupportClosureProvider | None = None
    candidate_validator: CandidateValidator | None = None
    secondary_support_threshold: float | None = None
    secondary_support_epsilon_mm: float = 1e-4


@dataclass(frozen=True)
class _ConstructionPortfolioResult:
    outcome: AlgorithmOutcome
    policy_metadata: dict[str, object]
    metadata: dict[str, object]
    incumbent_store: ValidatedIncumbentStore


class InventorySearchOrchestrator:
    """Compose inventory/subset workflow với executor của từng level.

    Module này không biết feasibility policy hay validator của level. Executor
    nhận subset policy và tự áp dụng constraint active; pipeline level vẫn chịu
    trách nhiệm independent validation của placement cuối.
    """

    def __init__(self, *, monotonic_clock: Callable[[], float] = perf_counter) -> None:
        self._clock = monotonic_clock
        self._consolidator = BoundedInventoryConsolidator(monotonic_clock=monotonic_clock)

    def execute(
        self,
        request: InventorySearchRequest,
        executor: InventoryConstructiveExecutor,
    ) -> AlgorithmOutcome:
        search = request.configuration
        if not search.enabled:
            raise ValueError("InventorySearchOrchestrator requires container_search.enabled=true")
        if request.algorithm_id not in request.supported_algorithm_ids:
            supported = ", ".join(sorted(request.supported_algorithm_ids))
            raise ValueError(
                "Inventory-aware container search currently supports only "
                f"{supported}; disable container_search or select a supported "
                f"algorithm instead of {request.algorithm_id!r}."
            )
        if request.candidate_validator is None:
            raise ValueError(
                "Inventory-aware search requires an independent candidate_validator"
            )

        pipeline_started = self._clock()
        global_deadline = (
            None
            if search.time_limit_seconds is None
            else pipeline_started + search.time_limit_seconds
        )
        search_deadline = (
            None
            if global_deadline is None
            else global_deadline - search.validation_reserve_seconds
        )
        construction_deadline = search_deadline
        if search_deadline is not None and search.consolidation.enabled:
            construction_deadline -= search.consolidation.time_limit_seconds
        budget = None
        if search_deadline is not None and global_deadline is not None:
            cardinality_count = max(1, len(search.limits.cardinalities))
            budget = SearchBudget(
                search_deadline_monotonic=search_deadline,
                total_deadline_monotonic=global_deadline,
                max_attempts=max(
                    1,
                    len(search.construction_item_order_variants)
                    * cardinality_count,
                ),
                max_subsets=max(
                    1, cardinality_count * search.max_candidates_per_count,
                ),
                max_item_orders=max(1, len(search.construction_item_order_variants)),
                max_container_orders=1,
                # Core constructors expose evaluated-candidate telemetry but do
                # not yet share one configurable global candidate cap. Keep the
                # time/subset/repair guards authoritative in this checkpoint.
                max_candidate_evaluations=2**63 - 1,
                max_repair_attempts=max(1, search.consolidation.max_candidates),
                max_no_improvement_attempts=max(1, search.consolidation.max_candidates),
                started_at_monotonic=pipeline_started,
                _clock=self._clock,
            )

        phase_started = self._clock()
        inventory = normalize_container_inventory(request.containers)
        normalization_seconds = self._clock() - phase_started
        if search.limits.max_used_container_count > inventory.physical_container_count:
            raise ValueError(
                "container_search.max_used_container_count="
                f"{search.limits.max_used_container_count} exceeds the available physical "
                f"inventory ({inventory.physical_container_count})."
            )

        phase_started = self._clock()
        precheck = run_hard_precheck(
            request.items,
            inventory,
            orientation_provider=request.orientation_provider,
        )
        precheck_seconds = self._clock() - phase_started
        phase_started = self._clock()
        lower_bound = estimate_container_lower_bound(request.items, inventory)
        lower_bound_seconds = self._clock() - phase_started
        phase_started = self._clock()
        capacity_limit = assess_capacity_within_container_limit(
            request.items,
            inventory,
            search.limits.max_used_container_count,
        )
        capacity_limit_seconds = self._clock() - phase_started
        all_precheck_issues = (*precheck.issues, *capacity_limit.issues)
        shared_metadata = {
            **search.metadata(),
            **inventory.metadata(),
            **lower_bound.metadata(),
            **capacity_limit.metadata(),
            "hard_precheck_valid": precheck.valid and capacity_limit.valid,
            "hard_precheck_issue_count": len(all_precheck_issues),
            "hard_precheck_issues": [asdict(value) for value in all_precheck_issues],
            "inventory_search_phase_runtime_seconds": {
                "normalization": normalization_seconds,
                "hard_precheck": precheck_seconds,
                "lower_bound": lower_bound_seconds,
                "capacity_limit": capacity_limit_seconds,
            },
        }
        if not precheck.valid or not capacity_limit.valid:
            return self._precheck_failure(request, shared_metadata)

        construction_started = self._clock()
        incumbent_store = ValidatedIncumbentStore(
            required_item_ids=[value.item_id for value in request.items],
            containers=request.containers,
            validator=request.candidate_validator,
            secondary_score_factory=(
                None
                if not search.secondary_search_score.enabled
                else lambda placements: calculate_secondary_search_score(
                    placements,
                    request.containers,
                    support_threshold=request.secondary_support_threshold,
                    support_epsilon_mm=request.secondary_support_epsilon_mm,
                )
            ),
        )
        construction = self._run_construction_portfolio(
            request=request,
            executor=executor,
            search_deadline=construction_deadline,
            incumbent_store=incumbent_store,
            search_budget=budget,
            inventory=inventory,
            aggregate_lower_bound=lower_bound.aggregate_lower_bound,
        )
        outcome = construction.outcome
        baseline_policy_metadata = construction.policy_metadata
        construction_runtime = self._clock() - construction_started
        consolidation = self._consolidator.execute(
            baseline=outcome,
            items=request.items,
            containers=request.containers,
            settings=request.settings,
            search=search,
            aggregate_lower_bound=lower_bound.aggregate_lower_bound,
            executor=executor,
            global_deadline_monotonic=search_deadline,
            support_closure_provider=request.support_closure_provider,
            candidate_validator=request.candidate_validator,
            incumbent_store=construction.incumbent_store,
            search_budget=budget,
            orientation_provider=request.orientation_provider,
        )
        outcome = consolidation.outcome
        consolidated = (
            consolidation.metadata["container_consolidation_final_count"]
            < consolidation.metadata["container_consolidation_initial_count"]
        )
        # Inventory/precheck evidence is computed before executor invocation and
        # remains authoritative even if an executor exits before iterating policy.
        final_metadata = {
            **outcome.metadata,
            **({} if consolidated else baseline_policy_metadata),
            **shared_metadata,
            **construction.metadata,
            **consolidation.metadata,
            **construction.incumbent_store.metadata(),
            "shared_search_budget": None if budget is None else budget.snapshot(),
            "container_consolidation_baseline_subset_evidence": baseline_policy_metadata,
        }
        final_metadata["selected_inventory_type_distribution"] = (
            _selected_type_distribution(inventory, outcome.placements)
        )
        final_metadata["inventory_search_phase_runtime_seconds"] = {
            **shared_metadata["inventory_search_phase_runtime_seconds"],
            "construction": construction_runtime,
            "incumbent_improvement": consolidation.metadata.get(
                "container_consolidation_runtime_seconds", 0.0,
            ),
            "total_search": self._clock() - pipeline_started,
        }
        final_metadata["inventory_search_termination_reason"] = (
            construction.metadata["inventory_construction_termination_reason"]
            if construction.incumbent_store.outcome is None
            else consolidation.metadata[
                "container_consolidation_termination_reason"
            ]
        )
        if outcome.solve.status in {"INFEASIBLE_HEURISTIC", "TIME_LIMIT"}:
            _add_incomplete_diagnostics(
                final_metadata,
                items=request.items,
                lower_bound=lower_bound.aggregate_lower_bound,
                cardinalities=search.limits.cardinalities,
                solve_status=outcome.solve.status,
            )
        return AlgorithmOutcome(
            solve=outcome.solve,
            placements=outcome.placements,
            backend=outcome.backend,
            metadata=final_metadata,
        )

    def _run_construction_portfolio(
        self,
        *,
        request: InventorySearchRequest,
        executor: InventoryConstructiveExecutor,
        search_deadline: float | None,
        incumbent_store: ValidatedIncumbentStore,
        search_budget: SearchBudget | None,
        inventory: NormalizedContainerInventory,
        aggregate_lower_bound: int,
    ) -> "_ConstructionPortfolioResult":
        variants = request.configuration.construction_item_order_variants
        acquisition = request.configuration.incumbent_acquisition
        use_acquisition = (
            acquisition.enabled
            and inventory.physical_container_count
            > request.configuration.exhaustive_max_containers
        )
        acquisition_ladder = (
            midpoint_cardinality_ladder(
                max(
                    aggregate_lower_bound,
                    request.configuration.limits.initial_used_container_count,
                ),
                request.configuration.limits.max_used_container_count,
            )
            if use_acquisition else ()
        )
        outcomes: list[tuple[str, AlgorithmOutcome, dict[str, object]]] = []
        variant_rows: list[dict[str, object]] = []
        acquired_cardinality: int | None = None
        complete_tie_break_portfolio = (
            request.configuration.secondary_search_score.enabled
            and request.configuration.secondary_search_score.complete_first_cardinality_portfolio
        )
        for index, variant in enumerate(variants):
            if search_budget is not None:
                if search_budget.search_time_exhausted():
                    break
                search_budget.record_item_order()
            now = self._clock()
            if search_deadline is not None and now >= search_deadline:
                break
            phase_deadline = search_deadline
            if search_deadline is not None:
                remaining_variants = len(variants) - index
                phase_deadline = now + (search_deadline - now) / remaining_variants
            target_cardinalities: tuple[int | None, ...] = (
                (acquired_cardinality,)
                if acquired_cardinality is not None
                else tuple(acquisition_ladder) if use_acquisition else (None,)
            )
            for target_cardinality in target_cardinalities:
                if search_budget is not None:
                    if not search_budget.can_start_attempt():
                        break
                    search_budget.record_attempt()
                if phase_deadline is not None and self._clock() >= phase_deadline:
                    break
                policy = LazyRankedContainerSubsetPolicy(
                    request.configuration.limits,
                    orientation_provider=request.orientation_provider,
                    exhaustive_max_containers=request.configuration.exhaustive_max_containers,
                    max_candidates_per_count=(
                        acquisition.max_subsets_per_cardinality
                        if use_acquisition
                        else request.configuration.max_candidates_per_count
                    ),
                    neighborhood_width=request.configuration.neighborhood_width,
                    composition_beam_width=request.configuration.composition_beam_width,
                    soft_volume_buffer_ratio=request.configuration.soft_volume_buffer_ratio,
                    deadline_monotonic=phase_deadline,
                    monotonic_clock=self._clock,
                    candidate_mode=(
                        "incumbent_acquisition" if use_acquisition else "portfolio"
                    ),
                    cardinalities_override=(
                        None
                        if target_cardinality is None
                        else (target_cardinality,)
                    ),
                )
                selected_settings = dict(request.settings)
                if variant != "current":
                    selected_settings["item_order_override"] = inventory_item_order(
                        request.items, variant,
                    )
                if phase_deadline is not None:
                    selected_settings["constructive_deadline_monotonic"] = phase_deadline
                started = self._clock()
                outcome = executor(
                    request.items,
                    request.containers,
                    selected_settings,
                    container_subset_policy=policy,
                )
                policy_metadata = policy.metadata()
                if search_budget is not None:
                    search_budget.record_subset(int(
                        outcome.metadata.get("candidate_subsets_evaluated", 0)
                    ))
                    search_budget.record_candidate(int(
                        outcome.metadata.get("candidate_feasibility_checks", 0)
                    ))
                outcomes.append((variant, outcome, policy_metadata))
                accepted_as_incumbent = incumbent_store.consider(outcome)
                variant_rows.append({
                    "phase": (
                        "incumbent_acquisition" if use_acquisition else "portfolio"
                    ),
                    "target_cardinality": target_cardinality,
                    "item_order": variant,
                    "status": outcome.solve.status,
                    "runtime_seconds": self._clock() - started,
                    "candidate_subsets_evaluated": outcome.metadata.get(
                        "candidate_subsets_evaluated", 0,
                    ),
                    "packing_attempts": outcome.metadata.get("packing_attempts", 0),
                    "best_partial_placement_count": outcome.metadata.get(
                        "best_partial_placement_count", len(outcome.placements),
                    ),
                    "independent_validation_status": (
                        "VALID" if accepted_as_incumbent
                        else "NOT_BETTER_OR_INVALID"
                        if outcome.solve.status == "FEASIBLE"
                        else "NOT_RUN"
                    ),
                    "policy": policy_metadata,
                })
                if accepted_as_incumbent:
                    if acquired_cardinality is None:
                        acquired_cardinality = (
                            incumbent_store.objective.used_container_count
                            if incumbent_store.objective is not None
                            else target_cardinality
                        )
                    break
            if incumbent_store.outcome is not None and not complete_tie_break_portfolio:
                break

        if not outcomes:
            return _ConstructionPortfolioResult(
                outcome=_time_limit_outcome(request),
                policy_metadata={},
                metadata={
                    "inventory_construction_variants_attempted": [],
                    "inventory_construction_termination_reason": "search_time_limit",
                },
                incumbent_store=incumbent_store,
            )
        if incumbent_store.outcome is not None:
            selected = next(
                value for value in outcomes if value[1] is incumbent_store.outcome
            )
            termination = "valid_solution_found"
        else:
            selected = max(
                outcomes,
                key=lambda value: int(value[1].metadata.get(
                    "best_partial_placement_count", len(value[1].placements),
                )),
            )
            if search_deadline is not None and self._clock() >= search_deadline:
                selected = (
                    selected[0],
                    _time_limit_outcome(request, template=selected[1]),
                    selected[2],
                )
                termination = "search_time_limit"
            elif any(
                _policy_candidate_budget_truncated(value[2]) for value in outcomes
            ):
                termination = "candidate_budget_exhausted"
            else:
                termination = "bounded_search_space_exhausted"
        return _ConstructionPortfolioResult(
            outcome=selected[1],
            policy_metadata=selected[2],
            metadata={
                "inventory_construction_item_order_selected": selected[0],
                "inventory_construction_variants_attempted": variant_rows,
                "inventory_construction_termination_reason": termination,
                "inventory_construction_variant_count": len(variant_rows),
                "incumbent_acquisition_used": use_acquisition,
                "incumbent_acquisition_cardinality_ladder": list(
                    acquisition_ladder
                ),
                "incumbent_acquisition_attempt_count": sum(
                    row["phase"] == "incumbent_acquisition"
                    for row in variant_rows
                ),
                "secondary_search_score_portfolio_completed": bool(
                    complete_tie_break_portfolio
                    and incumbent_store.outcome is not None
                ),
                "secondary_search_score_first_valid_cardinality": (
                    acquired_cardinality
                ),
                "container_type_compositions_evaluated_total": sum(
                    int(row["policy"].get("container_subset_candidates_generated", 0))
                    for row in variant_rows
                ),
                "duplicate_physical_subsets_avoided_total": sum(
                    int(row["policy"].get("duplicate_physical_subsets_avoided", 0))
                    for row in variant_rows
                ),
            },
            incumbent_store=incumbent_store,
        )

    @staticmethod
    def _precheck_failure(
        request: InventorySearchRequest,
        metadata: dict[str, Any],
    ) -> AlgorithmOutcome:
        issues = metadata["hard_precheck_issues"]
        return AlgorithmOutcome(
            solve=SolveResult(
                status="PRECHECK_FAILED",
                message=(
                    "Hard input/capacity precheck rejected the "
                    f"{request.precheck_failure_context}: "
                    + "; ".join(str(value["message"]) for value in issues)
                ),
                objective_value=None,
                vector=None,
                raw_result=OptimizeResult(),
            ),
            placements=[],
            backend=request.precheck_backend,
            metadata={
                **metadata,
                "failure_class": _precheck_failure_class(issues),
                "failure_interpretation": "proven_input_or_aggregate_capacity_failure",
                "construction_complete": False,
                "construction_termination_reason": "hard_precheck_failed",
                "unpacked_item_count": len(request.items),
                "unpacked_items": [
                    {"item_id": value.item_id, "reason_code": "HARD_PRECHECK_FAILED"}
                    for value in request.items
                ],
            },
        )


def _selected_type_distribution(
    inventory: NormalizedContainerInventory,
    placements: list[Placement],
) -> list[dict[str, object]]:
    selected_ids = {value.container_id for value in placements}
    distribution: list[dict[str, object]] = []
    for group in inventory.groups:
        group_ids = [
            container_id
            for container_id in group.physical_container_ids
            if container_id in selected_ids
        ]
        if group_ids:
            distribution.append({
                "equivalent_type_id": group.type_id,
                "display_type_id": group.display_type_id,
                "declared_type_ids": list(group.declared_type_ids),
                "physical_container_ids": group_ids,
                "quantity": len(group_ids),
            })
    return distribution


def _precheck_failure_class(issues: list[dict[str, object]]) -> str:
    codes = {str(value.get("code")) for value in issues}
    if codes & {
        "INSUFFICIENT_VOLUME_WITHIN_CONTAINER_LIMIT",
        "INSUFFICIENT_PAYLOAD_WITHIN_CONTAINER_LIMIT",
        "INSUFFICIENT_TOTAL_VOLUME",
        "INSUFFICIENT_TOTAL_CAPACITY",
    }:
        return "CAPACITY_LIMIT_PROVEN"
    if codes & {"ITEM_TOO_LARGE", "ITEM_TOO_HEAVY", "NO_ALLOWED_ORIENTATION"}:
        return "ITEM_INCOMPATIBLE"
    return "INPUT_INVALID"


def _policy_candidate_budget_truncated(metadata: dict[str, object]) -> bool:
    limit = int(metadata.get("container_subset_max_candidates_per_count", 0) or 0)
    by_cardinality = metadata.get("container_type_compositions_by_cardinality", {})
    return bool(
        limit
        and isinstance(by_cardinality, dict)
        and any(int(value) > limit for value in by_cardinality.values())
    )


def _outcome_rank(
    outcome: AlgorithmOutcome, containers: list[Container],
) -> tuple[object, ...]:
    used_ids = {value.container_id for value in outcome.placements}
    costs = {value.container_id: value.cost for value in containers}
    return (
        len(used_ids),
        sum(costs[container_id] for container_id in used_ids),
        tuple(sorted(used_ids)),
    )


def _time_limit_outcome(
    request: InventorySearchRequest,
    *,
    template: AlgorithmOutcome | None = None,
) -> AlgorithmOutcome:
    return AlgorithmOutcome(
        solve=SolveResult(
            status="TIME_LIMIT",
            message=(
                "Inventory-aware bounded search reached its global construction "
                "deadline before finding a complete packing."
            ),
            objective_value=None,
            vector=None,
            raw_result=OptimizeResult(),
        ),
        placements=[],
        backend=(request.precheck_backend if template is None else template.backend),
        metadata={} if template is None else dict(template.metadata),
    )


def _add_incomplete_diagnostics(
    metadata: dict[str, Any],
    *,
    items: list[Item],
    lower_bound: int,
    cardinalities: Collection[int],
    solve_status: str,
) -> None:
    if lower_bound > max(cardinalities):
        reason = "container_count_limit_below_aggregate_lower_bound"
        item_reason = "CONTAINER_COUNT_LIMIT_BELOW_LOWER_BOUND"
    elif solve_status == "TIME_LIMIT":
        reason = "time_limit_reached"
        item_reason = "TIME_LIMIT_REACHED"
    else:
        reason = "heuristic_search_exhausted"
        item_reason = "NO_COMPLETE_PACKING_FOUND"
    metadata.setdefault("construction_complete", False)
    inventory_reason = str(metadata.get("inventory_construction_termination_reason", ""))
    metadata.setdefault("failure_class", (
        "CAPACITY_LIMIT_PROVEN"
        if reason == "container_count_limit_below_aggregate_lower_bound"
        else "TIME_LIMIT"
        if reason == "time_limit_reached"
        else "CANDIDATE_BUDGET_EXHAUSTED"
        if inventory_reason == "candidate_budget_exhausted"
        else "HEURISTIC_SEARCH_EXHAUSTED"
    ))
    metadata.setdefault("construction_termination_reason", reason)
    metadata.setdefault("unpacked_item_count", len(items))
    metadata.setdefault("unpacked_items", [
        {"item_id": value.item_id, "reason_code": item_reason}
        for value in items
    ])
