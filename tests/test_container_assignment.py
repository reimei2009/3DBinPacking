from __future__ import annotations

from time import perf_counter

import pytest

from container_packing.algorithms.heuristics.container_assignment import (
    ContainerAffinity,
    ContainerAffinityPlan,
    ContainerPreferencePolicy,
    StopAwareBeamAssignmentPlanner,
)
from container_packing.algorithms.heuristics.extreme_point_best_fit import (
    pack_order_best_fit,
    solve,
)
from container_packing.algorithms.heuristics.extreme_point_core import SearchStats
from container_packing.algorithms.feasibility import FixedOrientationFeasibilityPolicy
from container_packing.schemas import Container, Item


def _container(container_id: str, *, payload: float = 20) -> Container:
    return Container(
        container_id, 1000, 1000, 1000, payload, 100, volume_m3=1.0
    )


def _item(item_id: str, stop: str, priority: int, *, weight: float = 5) -> Item:
    return Item(
        item_id, 100, 100, 100, weight,
        source={
            "delivery_stop_id": stop,
            "delivery_priority": priority,
            "delivery_data_source": "test",
        },
    )


def test_stop_aware_plans_are_complete_deterministic_and_use_fixed_subset() -> None:
    items = [
        _item("A1", "A", 1), _item("A2", "A", 1),
        _item("B1", "B", 2), _item("B2", "B", 2),
    ]
    containers = (_container("C1", payload=10), _container("C2", payload=10))
    first = StopAwareBeamAssignmentPlanner(beam_width=16, max_plans_per_subset=8)
    second = StopAwareBeamAssignmentPlanner(beam_width=16, max_plans_per_subset=8)

    first_plans = first.plans(containers, items)
    second_plans = second.plans(containers, items)

    assert first_plans
    assert [value.signature for value in first_plans] == [
        value.signature for value in second_plans
    ]
    assert all(set(value.by_item_id) == {item.item_id for item in items} for value in first_plans)
    assert all(
        set(affinity.ranked_container_ids) == {"C1", "C2"}
        for value in first_plans
        for affinity in value.affinities
    )
    assert first_plans[0].planned_stop_fragmentation == 0


def test_stop_aware_planner_prunes_capacity_and_oversized_items() -> None:
    containers = (_container("C1", payload=5), _container("C2", payload=5))
    capacity_items = [
        _item("A", "A", 1, weight=5),
        _item("B", "B", 2, weight=5),
        _item("C", "C", 3, weight=1),
    ]
    planner = StopAwareBeamAssignmentPlanner()

    assert planner.plans(containers, capacity_items) == ()
    assert planner.metadata()["container_assignment_states_capacity_pruned"] > 0

    oversized = Item(
        "BIG", 2000, 100, 100, 1,
        source={"delivery_stop_id": "A", "delivery_priority": 1},
    )
    fit_planner = StopAwareBeamAssignmentPlanner()
    assert fit_planner.plans(containers, [oversized]) == ()
    assert fit_planner.metadata()["container_assignment_states_fit_pruned"] == 2


def _affinity_plan(*affinities: ContainerAffinity) -> ContainerAffinityPlan:
    return ContainerAffinityPlan(
        container_subset_ids=("C1", "C2"),
        affinities=affinities,
        score=(2, 0, 200),
        planned_used_container_count=2,
        planned_stop_fragmentation=0,
        total_cost=200,
        maximum_utilization=0.5,
        utilization_imbalance=0.0,
    )


def test_preference_policy_allows_fallback_but_never_outside_fixed_subset() -> None:
    policy = ContainerPreferencePolicy(_affinity_plan(ContainerAffinity(
        "A", "STOP-A", ("A",), ("C1", "C2"),
    )))
    item = _item("A", "STOP-A", 1)

    assert policy.allows(item, "C1")
    assert policy.allows(item, "C2")
    assert not policy.allows(item, "C3")
    assert policy.rank(item, "C1") == 0
    assert policy.rank(item, "C2") == 1


def test_explicit_order_is_not_split_after_first_item_selection() -> None:
    first = _item("A1", "STOP-A", 1)
    second = _item("A2", "STOP-A", 1)
    first.source["order_id"] = second.source["order_id"] = "ORDER-A"
    policy = ContainerPreferencePolicy(_affinity_plan(ContainerAffinity(
        "ORDER-A", "STOP-A", ("A1", "A2"), ("C1", "C2"),
    )))

    policy.record_selection(first, "C2")

    assert policy.allows(second, "C2")
    assert not policy.allows(second, "C1")


def test_best_fit_uses_fallback_when_preferred_container_is_not_feasible() -> None:
    item = Item(
        "A", 800, 800, 800, 5,
        source={"delivery_stop_id": "STOP-A", "delivery_priority": 1},
    )
    small = Container("C1", 500, 500, 500, 20, 100, volume_m3=0.125)
    large = _container("C2")
    preference = ContainerPreferencePolicy(_affinity_plan(ContainerAffinity(
        "A", "STOP-A", ("A",), ("C1", "C2"),
    )))

    placements = pack_order_best_fit(
        [item], (small, large), 1e-6, SearchStats(),
        FixedOrientationFeasibilityPolicy(),
        container_preference_policy=preference,
    )

    assert placements is not None
    assert placements[0].container_id == "C2"
    assert preference.metadata(placements)["container_affinity_fallback_count"] == 1


def test_order_group_metadata_is_required_to_group_items() -> None:
    legacy = [_item("A1", "STOP-A", 1), _item("A2", "STOP-A", 1)]
    explicit = [_item("B1", "STOP-B", 2), _item("B2", "STOP-B", 2)]
    explicit[0].source["order_id"] = explicit[1].source["order_id"] = "ORDER-B"
    planner = StopAwareBeamAssignmentPlanner(beam_width=16, max_plans_per_subset=8)

    plan = planner.plans((_container("C1", payload=10), _container("C2", payload=10)), legacy + explicit)[0]

    by_group = {value.group_id: value.item_ids for value in plan.affinities}
    assert by_group["A1"] == ("A1",)
    assert by_group["A2"] == ("A2",)
    assert by_group["ORDER-B"] == ("B1", "B2")


def test_affinity_plan_rejects_incomplete_or_duplicate_subset_rank() -> None:
    with pytest.raises(ValueError, match="rank every fixed-subset container"):
        _affinity_plan(ContainerAffinity(
            "A", "STOP-A", ("A",), ("C1",),
        ))


def test_stop_aware_planner_honors_expired_deadline() -> None:
    planner = StopAwareBeamAssignmentPlanner()

    plans = planner.plans(
        (_container("C1"), _container("C2")),
        [_item("A", "STOP-A", 1)],
        deadline_monotonic=perf_counter() - 1.0,
    )

    assert plans == ()
    assert planner.metadata()["container_assignment_deadline_reached"] is True
    assert planner.metadata()["container_assignment_termination_reason"] == "deadline_reached"


def test_best_fit_without_assignment_planner_keeps_legacy_signature() -> None:
    items = [_item("A", "A", 1), _item("B", "B", 2)]
    containers = [_container("C1"), _container("C2")]

    baseline = solve(items, containers)
    explicit_none = solve(items, containers, container_assignment_planner=None)

    assert baseline.solve.status == explicit_none.solve.status == "FEASIBLE"
    assert [
        (value.item_id, value.container_id, value.x_mm, value.y_mm, value.z_mm)
        for value in baseline.placements
    ] == [
        (value.item_id, value.container_id, value.x_mm, value.y_mm, value.z_mm)
        for value in explicit_none.placements
    ]


def test_beam_assignment_recovers_geometry_that_global_greedy_misses() -> None:
    dimensions = [(3, 8), (3, 8), (5, 7), (8, 3), (3, 6)]
    items = [
        Item(
            f"I{index}", length, width, 1, 1,
            source={
                "delivery_stop_id": f"S{index % 3}",
                "delivery_priority": index % 3 + 1,
            },
        )
        for index, (length, width) in enumerate(dimensions)
    ]
    containers = [
        Container("C1", 10, 10, 1, 100, 1, volume_m3=1e-7),
        Container("C2", 10, 10, 1, 100, 1, volume_m3=1e-7),
    ]

    greedy = solve(items, containers)
    assigned = solve(
        items,
        containers,
        container_assignment_planner=StopAwareBeamAssignmentPlanner(
            beam_width=64, max_plans_per_subset=32
        ),
    )

    assert greedy.solve.status == "INFEASIBLE_HEURISTIC"
    assert assigned.solve.status == "FEASIBLE"
    assert {value.container_id for value in assigned.placements} == {"C1", "C2"}
    assert assigned.metadata["container_assignment_plans_evaluated"] > 0
