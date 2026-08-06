"""Điều phối bounded inventory search độc lập với constraint từng level."""

from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Any, Protocol

from scipy.optimize import OptimizeResult

from ..contracts import AlgorithmOutcome
from ...schemas import Container, Item, Placement, SolveResult
from .configuration import ContainerSearchConfiguration
from .inventory import NormalizedContainerInventory, normalize_container_inventory
from .precheck import estimate_container_lower_bound, run_hard_precheck
from .subset_generation import LazyRankedContainerSubsetPolicy


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
    precheck_backend: str = "inventory-aware-precheck"
    precheck_failure_context: str = "inventory instance"


class InventorySearchOrchestrator:
    """Compose inventory/subset workflow với executor của từng level.

    Module này không biết feasibility policy hay validator của level. Executor
    nhận subset policy và tự áp dụng constraint active; pipeline level vẫn chịu
    trách nhiệm independent validation của placement cuối.
    """

    def __init__(self, *, monotonic_clock: Callable[[], float] = perf_counter) -> None:
        self._clock = monotonic_clock

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
        precheck = run_hard_precheck(request.items, inventory)
        precheck_seconds = self._clock() - phase_started
        phase_started = self._clock()
        lower_bound = estimate_container_lower_bound(request.items, inventory)
        lower_bound_seconds = self._clock() - phase_started
        shared_metadata = {
            **search.metadata(),
            **inventory.metadata(),
            **lower_bound.metadata(),
            "hard_precheck_valid": precheck.valid,
            "hard_precheck_issue_count": len(precheck.issues),
            "hard_precheck_issues": [asdict(value) for value in precheck.issues],
            "hide_objective_when_invalid": True,
            "inventory_search_phase_runtime_seconds": {
                "normalization": normalization_seconds,
                "hard_precheck": precheck_seconds,
                "lower_bound": lower_bound_seconds,
            },
        }
        if not precheck.valid:
            return self._precheck_failure(request, shared_metadata)

        deadline = (
            None
            if search.time_limit_seconds is None
            else self._clock() + search.time_limit_seconds
        )
        policy = LazyRankedContainerSubsetPolicy(
            search.limits,
            exhaustive_max_containers=search.exhaustive_max_containers,
            max_candidates_per_count=search.max_candidates_per_count,
            neighborhood_width=search.neighborhood_width,
            soft_volume_buffer_ratio=search.soft_volume_buffer_ratio,
            deadline_monotonic=deadline,
        )
        selected_settings = dict(request.settings)
        if deadline is not None:
            selected_settings["constructive_deadline_monotonic"] = deadline

        construction_started = self._clock()
        outcome = executor(
            request.items,
            request.containers,
            selected_settings,
            container_subset_policy=policy,
        )
        # Inventory/precheck evidence is computed before executor invocation and
        # remains authoritative even if an executor exits before iterating policy.
        final_metadata = {**outcome.metadata, **policy.metadata(), **shared_metadata}
        final_metadata["selected_inventory_type_distribution"] = (
            _selected_type_distribution(inventory, outcome.placements)
        )
        final_metadata["inventory_search_phase_runtime_seconds"] = {
            **shared_metadata["inventory_search_phase_runtime_seconds"],
            "construction": self._clock() - construction_started,
        }
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
    metadata.setdefault("construction_termination_reason", reason)
    metadata.setdefault("unpacked_item_count", len(items))
    metadata.setdefault("unpacked_items", [
        {"item_id": value.item_id, "reason_code": item_reason}
        for value in items
    ])
