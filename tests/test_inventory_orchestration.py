from __future__ import annotations

from typing import Any

import pytest
from scipy.optimize import OptimizeResult

from container_packing.algorithms.contracts import AlgorithmOutcome
from container_packing.algorithms.search import (
    ContainerSearchConfiguration,
    InventorySearchOrchestrator,
    InventorySearchRequest,
)
from container_packing.schemas import Container, Item, Placement, SolveResult


def _configuration(*, time_limit_seconds: float | None = 5.0) -> ContainerSearchConfiguration:
    return ContainerSearchConfiguration.from_mapping({
        "enabled": True,
        "initial_used_container_count": 1,
        "max_used_container_count": 1,
        "automatically_increase_container_count": False,
        "time_limit_seconds": time_limit_seconds,
    })


def _request(
    *,
    items: list[Item] | None = None,
    containers: list[Container] | None = None,
    algorithm_id: str = "extreme_point_best_fit",
    configuration: ContainerSearchConfiguration | None = None,
) -> InventorySearchRequest:
    return InventorySearchRequest(
        algorithm_id=algorithm_id,
        items=items or [Item("I1", 10, 10, 10, 1)],
        containers=containers or [Container(
            "C1", 100, 100, 100, 100, 10, volume_m3=0.001,
            source={"container_type_id": "BOX-A"},
        )],
        settings={"caller_setting": "preserved"},
        configuration=configuration or _configuration(),
        supported_algorithm_ids=frozenset({"extreme_point_best_fit", "extreme_point_ffd"}),
    )


def _feasible_outcome() -> AlgorithmOutcome:
    return AlgorithmOutcome(
        solve=SolveResult("FEASIBLE", "complete", 10.0, None, OptimizeResult()),
        placements=[Placement("I1", "C1", 0, 0, 0, 10, 10, 10, 1)],
        backend="test-executor",
        metadata={"executor_metadata": "kept"},
    )


def test_orchestrator_preserves_executor_output_and_adds_inventory_evidence() -> None:
    captured: dict[str, Any] = {}

    def executor(items, containers, settings, *, container_subset_policy):
        captured["settings"] = settings
        captured["policy"] = container_subset_policy
        return _feasible_outcome()

    outcome = InventorySearchOrchestrator(monotonic_clock=lambda: 100.0).execute(
        _request(), executor,
    )

    assert outcome.solve.status == "FEASIBLE"
    assert outcome.placements == _feasible_outcome().placements
    assert outcome.metadata["executor_metadata"] == "kept"
    assert outcome.metadata["hard_precheck_valid"] is True
    assert outcome.metadata["inventory_physical_container_count"] == 1
    assert len(outcome.metadata["inventory_fingerprint"]) == 64
    assert outcome.metadata["selected_inventory_type_distribution"] == [{
        "equivalent_type_id": outcome.metadata["inventory_container_types"][0]["type_id"],
        "display_type_id": "BOX-A",
        "declared_type_ids": ["BOX-A"],
        "physical_container_ids": ["C1"],
        "quantity": 1,
    }]
    assert captured["settings"]["caller_setting"] == "preserved"
    assert captured["settings"]["constructive_deadline_monotonic"] == 105.0
    assert captured["policy"].deadline_monotonic == 105.0


def test_orchestrator_rejects_unsupported_algorithm_before_executor() -> None:
    called = False

    def executor(*args, **kwargs):
        nonlocal called
        called = True
        return _feasible_outcome()

    with pytest.raises(ValueError, match="currently supports only"):
        InventorySearchOrchestrator().execute(
            _request(algorithm_id="milp_big_m"), executor,
        )
    assert called is False


def test_orchestrator_precheck_failure_does_not_call_executor() -> None:
    called = False

    def executor(*args, **kwargs):
        nonlocal called
        called = True
        return _feasible_outcome()

    outcome = InventorySearchOrchestrator(monotonic_clock=lambda: 1.0).execute(
        _request(items=[Item("OVERSIZED", 200, 10, 10, 1)]), executor,
    )

    assert called is False
    assert outcome.solve.status == "PRECHECK_FAILED"
    assert outcome.solve.objective_value is None
    assert outcome.backend == "inventory-aware-precheck"
    assert outcome.metadata["construction_termination_reason"] == "hard_precheck_failed"
    assert outcome.metadata["unpacked_items"] == [{
        "item_id": "OVERSIZED", "reason_code": "HARD_PRECHECK_FAILED",
    }]


def test_orchestrator_keeps_time_limit_failure_as_non_proven_diagnostic() -> None:
    def executor(items, containers, settings, *, container_subset_policy):
        return AlgorithmOutcome(
            solve=SolveResult("TIME_LIMIT", "budget", None, None, OptimizeResult()),
            placements=[], backend="test-executor", metadata={},
        )

    outcome = InventorySearchOrchestrator(monotonic_clock=lambda: 5.0).execute(
        _request(), executor,
    )

    assert outcome.solve.status == "TIME_LIMIT"
    assert outcome.solve.objective_value is None
    assert outcome.metadata["construction_termination_reason"] == "time_limit_reached"
    assert outcome.metadata["unpacked_items"][0]["reason_code"] == "TIME_LIMIT_REACHED"


def test_orchestrator_requires_enabled_configuration() -> None:
    disabled = ContainerSearchConfiguration.from_mapping({"enabled": False})
    with pytest.raises(ValueError, match="enabled=true"):
        InventorySearchOrchestrator().execute(
            _request(configuration=disabled), lambda *args, **kwargs: _feasible_outcome(),
        )
