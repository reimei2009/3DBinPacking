from __future__ import annotations

import os

import pytest

from container_packing.algorithms.heuristics.maximal_space_best_fit import solve
from container_packing.runtime import deadline_reliability as reliability
from container_packing.runtime.deadline_reliability import DeadlineReliabilityObserver
from container_packing.schemas import Container, Item
from container_packing.data_loader import load_config
from container_packing.levels.level_04_algorithms import execute_level_04
from container_packing.levels.level_05_algorithms import execute_level_05


class MutableClock:
    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


def observer(clocks: list[MutableClock]) -> DeadlineReliabilityObserver:
    return DeadlineReliabilityObserver(
        enabled=True,
        deadline_monotonic=100.0,
        wall_clock=clocks[0], monotonic_clock=clocks[1],
        process_clock=clocks[2], active_clock=clocks[3],
        active_clock_source="fake",
    )


def test_deadline_observer_classifies_normal_suspend_contention_and_clock_jump() -> None:
    normal = [MutableClock() for _ in range(4)]
    measured = observer(normal)
    for clock in normal:
        clock.value = 0.5
    assert measured.metadata()["deadline_reliability_classification"] == "NORMAL"

    suspended = [MutableClock() for _ in range(4)]
    measured = observer(suspended)
    suspended[0].value = suspended[1].value = 10
    suspended[2].value = 0.1
    suspended[3].value = 0.2
    payload = measured.metadata()
    assert payload["deadline_reliability_classification"] == "SYSTEM_SUSPEND_DETECTED"
    assert payload["deadline_reliability_evidence_eligible"] is False

    contention = [MutableClock() for _ in range(4)]
    measured = observer(contention)
    contention[0].value = contention[1].value = contention[3].value = 10
    contention[2].value = 0.1
    assert measured.metadata()["deadline_reliability_classification"] == "HOST_CONTENTION_SUSPECTED"

    jumped = [MutableClock() for _ in range(4)]
    measured = observer(jumped)
    jumped[0].value = 5
    jumped[1].value = jumped[3].value = jumped[2].value = 1
    assert measured.metadata()["deadline_reliability_classification"] == "CLOCK_DISCONTINUITY"


def test_deadline_observer_finds_long_non_interruptible_operation() -> None:
    clocks = [MutableClock() for _ in range(4)]
    measured = observer(clocks)
    with measured.operation("load_transfer"):
        for clock in clocks:
            clock.value = 1.5
    payload = measured.metadata()
    assert payload["deadline_reliability_classification"] == "LONG_NON_INTERRUPTIBLE_OPERATION"
    assert payload["deadline_reliability_max_operation"] == "load_transfer"
    assert payload["deadline_reliability_max_operation_active_seconds"] == pytest.approx(1.5)


def test_portable_active_clock_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reliability.os, "name", "posix")
    clock, source = reliability.windows_unbiased_interrupt_clock()
    assert clock is None
    assert source == "portable_unavailable"


@pytest.mark.skipif(os.name != "nt", reason="Windows adapter contract")
def test_windows_unbiased_interrupt_clock_is_available_and_monotonic() -> None:
    clock, source = reliability.windows_unbiased_interrupt_clock()
    assert source == "windows_query_unbiased_interrupt_time"
    assert clock is not None
    assert clock() <= clock()


def test_mes_observer_does_not_change_solution_or_rejection_counters() -> None:
    items = [Item("A", 5, 5, 5, 1), Item("B", 5, 5, 5, 1)]
    containers = [Container("C", 10, 10, 10, 100, 1, volume_m3=1e-6)]
    baseline = solve(items, containers, {"subset_enumeration_limit": 4})
    observed = solve(items, containers, {
        "subset_enumeration_limit": 4,
        "deadline_reliability": {"enabled": True},
    })
    assert observed.solve.status == baseline.solve.status
    assert observed.placements == baseline.placements
    for key in (
        "candidate_feasibility_checks", "geometry_rejected_candidates",
        "empty_spaces_evaluated", "empty_spaces_pruned",
    ):
        assert observed.metadata[key] == baseline.metadata[key]
    assert observed.metadata["deadline_reliability_enabled"] is True


@pytest.mark.parametrize("level", [4, 5])
def test_mes_inventory_level4_level5_emits_reliability_evidence(
    root, level: int,
) -> None:
    items = [
        Item("BOTTOM", 20, 10, 5, 1, source={
            "stackability_code": "1", "max_stackability": "2",
        }),
        Item("TOP", 20, 10, 5, 1, source={
            "stackability_code": "1", "max_stackability": "2",
        }),
    ]
    containers = [
        Container("FIT", 10, 20, 10, 100, 1, volume_m3=2e-6),
    ]
    settings = {
        "support": {"threshold": 1.0, "epsilon_mm": 1e-4},
        "validation": {
            "coordinate_tolerance_mm": 1e-4,
            "weight_tolerance_kg": 1e-6,
            "load_tolerance_kg": 1e-6,
        },
        "stackability": load_config(root / "config/level_04/stackability_rules.yaml"),
        "load_bearing": load_config(root / "config/level_05/load_bearing_rules.yaml"),
        "deadline_reliability": {"enabled": True},
        "container_search": {
            "enabled": True,
            "initial_used_container_count": 1,
            "max_used_container_count": 1,
            "automatically_increase_container_count": False,
            "time_limit_seconds": 5,
            "validation_reserve_seconds": 0.1,
            "consolidation": {"enabled": False},
        },
    }
    executor = execute_level_04 if level == 4 else execute_level_05
    outcome = executor("maximal_space_best_fit", items, containers, settings)
    assert outcome.solve.status == "FEASIBLE"
    assert len(outcome.placements) == 2
    assert outcome.metadata["deadline_reliability_enabled"] is True
    assert outcome.metadata["deadline_reliability_checkpoint_count"] > 0
    assert outcome.metadata["deadline_reliability_active_clock_source"] in {
        "windows_query_unbiased_interrupt_time", "portable_unavailable",
        "windows_unavailable",
    }
