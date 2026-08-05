from __future__ import annotations

import pytest

from container_packing.algorithms.contracts import (
    ConstructionTerminationReason,
    SearchBudget,
    SearchTerminationReason,
)
from container_packing.algorithms.feasibility import FixedOrientationFeasibilityPolicy
from container_packing.algorithms.heuristics.extreme_point_core import (
    SearchStats,
    pack_order_first_fit,
)
from container_packing.algorithms.heuristics.extreme_point_ffd import solve_level1
from container_packing.reporting import solver_payload
from container_packing.schemas import Container, Item


class FakeClock:
    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


def _budget(clock: FakeClock) -> SearchBudget:
    return SearchBudget(
        started_at_monotonic=clock(),
        search_deadline_monotonic=5.0,
        total_deadline_monotonic=6.0,
        max_attempts=2,
        max_subsets=2,
        max_item_orders=2,
        max_container_orders=2,
        max_candidate_evaluations=3,
        max_repair_attempts=2,
        max_no_improvement_attempts=2,
        _clock=clock,
    )


def _container() -> Container:
    return Container("C1", 10, 10, 10, 100, 10, volume_m3=1e-6)


def test_search_budget_uses_injected_monotonic_clock_without_sleep() -> None:
    clock = FakeClock()
    budget = _budget(clock)

    assert budget.can_start_attempt()
    assert budget.stop_reason() is None

    clock.value = 5.0

    assert budget.search_time_exhausted()
    assert not budget.total_time_exhausted()
    assert budget.stop_reason() == SearchTerminationReason.TIME_LIMIT_REACHED

    clock.value = 6.0
    assert budget.total_time_exhausted()


def test_search_budget_validates_limits_and_reports_counter_gate() -> None:
    clock = FakeClock()
    budget = _budget(clock)

    assert budget.record_candidate(3)
    assert budget.stop_reason() == SearchTerminationReason.CANDIDATE_LIMIT_REACHED
    assert budget.snapshot()["candidate_evaluations"] == 3

    with pytest.raises(ValueError, match="must be positive"):
        SearchBudget(
            started_at_monotonic=0,
            search_deadline_monotonic=1,
            total_deadline_monotonic=2,
            max_attempts=0,
            max_subsets=1,
            max_item_orders=1,
            max_container_orders=1,
            max_candidate_evaluations=1,
            max_repair_attempts=1,
            max_no_improvement_attempts=1,
            _clock=clock,
        )


def test_first_fit_attempt_preserves_partial_placements_and_unpacked_evidence() -> None:
    items = [
        Item("FITS", 5, 5, 5, 1),
        Item("TOO_BIG", 11, 10, 10, 1),
    ]

    attempt = pack_order_first_fit(
        items,
        (_container(),),
        1e-6,
        SearchStats(),
        FixedOrientationFeasibilityPolicy(),
    )

    assert not attempt.complete
    assert [value.item_id for value in attempt.placements] == ["FITS"]
    assert attempt.failed_item_id == "TOO_BIG"
    assert attempt.termination_reason == ConstructionTerminationReason.NO_FEASIBLE_CANDIDATE
    assert [value.item_id for value in attempt.unpacked_items] == ["TOO_BIG"]
    assert attempt.unpacked_items[0].candidate_positions_tested > 0


def test_solver_does_not_publish_partial_attempt_as_feasible_solution() -> None:
    items = [
        Item("FITS", 5, 5, 5, 1),
        Item("TOO_BIG", 11, 10, 10, 1),
    ]
    outcome = solve_level1(
        items,
        [_container()],
        {"item_order_override": ["FITS", "TOO_BIG"]},
    )

    assert outcome.solve.status == "INFEASIBLE_HEURISTIC"
    assert outcome.solve.objective_value is None
    assert outcome.placements == []
    assert outcome.metadata["construction_complete"] is False
    assert outcome.metadata["best_partial_placement_count"] == 1
    assert outcome.metadata["unpacked_item_count"] == 1
    assert outcome.metadata["unpacked_items"][0]["item_id"] == "TOO_BIG"

    persisted = solver_payload({
        "status": outcome.solve.status,
        "objective_value": outcome.solve.objective_value,
        **outcome.metadata,
    })
    assert persisted.get("objective_value") is None
    assert persisted["construction_complete"] is False
    assert persisted["best_partial_placement_count"] == 1
    assert persisted["unpacked_items"][0]["reason_code"] == "NO_FEASIBLE_CANDIDATE"


def test_complete_attempt_remains_sequence_compatible_and_deterministic() -> None:
    items = [Item("A", 5, 5, 5, 1), Item("B", 5, 5, 5, 1)]
    first = pack_order_first_fit(
        items, (_container(),), 1e-6, SearchStats(),
        FixedOrientationFeasibilityPolicy(),
    )
    second = pack_order_first_fit(
        items, (_container(),), 1e-6, SearchStats(),
        FixedOrientationFeasibilityPolicy(),
    )

    assert first.complete
    assert list(first) == list(second)
    assert first.attempt_signature == second.attempt_signature
    assert first.statistics.candidate_positions_tested > 0
    assert first.unpacked_items == ()
