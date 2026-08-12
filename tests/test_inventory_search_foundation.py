from __future__ import annotations

from time import perf_counter

import pytest

from container_packing.algorithms.orientation import horizontal_orientation_provider
from container_packing.algorithms.heuristics.extreme_point_best_fit import solve
from container_packing.algorithms.search import (
    assess_capacity_within_container_limit,
    InventorySearchLimits,
    LazyRankedContainerSubsetPolicy,
    midpoint_cardinality_ladder,
    estimate_container_lower_bound,
    normalize_container_inventory,
    run_hard_precheck,
)
from container_packing.schemas import Container, Item


def _container(
    container_id: str,
    *,
    side: float = 10,
    payload: float = 100,
    cost: float = 10,
    available: int = 1,
    profile: str = "default",
) -> Container:
    return Container(
        container_id,
        side,
        side,
        side,
        payload,
        cost,
        availability=available,
        volume_m3=side ** 3 / 1_000_000_000,
        source={"constraint_profile_id": profile},
    )


def test_inventory_groups_equivalent_physical_instances_without_losing_quantity() -> None:
    containers = [_container(f"C{index:03d}") for index in range(500)]

    inventory = normalize_container_inventory(containers)

    assert inventory.physical_container_count == 500
    assert inventory.equivalent_type_count == 1
    assert inventory.groups[0].quantity == 500
    assert inventory.groups[0].physical_container_ids[0] == "C000"


def test_inventory_keeps_constraint_profiles_and_unavailable_instances_separate() -> None:
    inventory = normalize_container_inventory([
        _container("C1", profile="ambient"),
        _container("C2", profile="cold"),
        _container("C3", available=0),
    ])

    assert inventory.physical_container_count == 2
    assert inventory.equivalent_type_count == 2
    assert inventory.unavailable_container_ids == ("C3",)


def test_inventory_rejects_duplicate_physical_ids() -> None:
    with pytest.raises(ValueError, match="Duplicate container IDs"):
        normalize_container_inventory([_container("C1"), _container("C1")])


def test_inventory_limits_distinguish_strict_target_from_adaptive_growth() -> None:
    strict = InventorySearchLimits(1, 4, False)
    adaptive = InventorySearchLimits(1, 4, True)

    assert strict.cardinalities == (1,)
    assert adaptive.cardinalities == (1, 2, 3, 4)


def test_midpoint_cardinality_ladder_reaches_cap_deterministically() -> None:
    assert midpoint_cardinality_ladder(9, 15) == (9, 12, 14, 15)
    assert midpoint_cardinality_ladder(1, 1) == (1,)
    with pytest.raises(ValueError, match="0 < minimum <= maximum"):
        midpoint_cardinality_ladder(2, 1)


def test_hard_precheck_uses_declared_orientation_and_reports_proven_failures() -> None:
    inventory = normalize_container_inventory([_container("C1", side=10, payload=5)])
    rotated = Item("ROTATED", 8, 12, 5, 1)
    too_heavy = Item("HEAVY", 5, 5, 5, 6)
    too_large = Item("LARGE", 20, 20, 20, 1)

    fixed = run_hard_precheck([rotated], inventory)
    horizontal = run_hard_precheck(
        [rotated], inventory,
        orientation_provider=horizontal_orientation_provider(),
    )
    failures = run_hard_precheck([too_heavy, too_large], inventory)

    assert not fixed.valid
    assert {value.code for value in fixed.issues} == {"ITEM_TOO_LARGE"}
    assert horizontal.valid is False  # 12 mm still exceeds a 10 mm square floor.
    assert {value.code for value in failures.issues} >= {
        "ITEM_TOO_HEAVY", "ITEM_TOO_LARGE",
    }


def test_hard_precheck_accepts_horizontal_rotation_when_container_is_compatible() -> None:
    container = Container("C1", 12, 8, 5, 10, 10, volume_m3=4.8e-7)
    inventory = normalize_container_inventory([container])
    item = Item("ROTATED", 8, 12, 5, 1)

    assert not run_hard_precheck([item], inventory).valid
    assert run_hard_precheck(
        [item], inventory,
        orientation_provider=horizontal_orientation_provider(),
    ).valid


def test_lower_bound_uses_finite_heterogeneous_inventory_capacities() -> None:
    inventory = normalize_container_inventory([
        _container("C1", side=10, payload=10),
        _container("C2", side=10, payload=7),
        _container("C3", side=10, payload=3),
    ])
    items = [Item("A", 5, 5, 5, 8), Item("B", 5, 5, 5, 8)]

    estimate = estimate_container_lower_bound(items, inventory)

    assert estimate.payload_lower_bound == 2
    assert estimate.aggregate_lower_bound == 2
    assert estimate.attainable_by_aggregate_capacity


def test_capacity_limit_precheck_rejects_request_even_when_full_inventory_is_enough() -> None:
    inventory = normalize_container_inventory([
        _container("C1", side=10, payload=10),
        _container("C2", side=10, payload=10),
        _container("C3", side=10, payload=10),
    ])
    items = [Item("A", 10, 10, 10, 9), Item("B", 10, 10, 10, 9)]

    assessment = assess_capacity_within_container_limit(items, inventory, 1)

    assert not assessment.valid
    assert {value.code for value in assessment.issues} == {
        "INSUFFICIENT_VOLUME_WITHIN_CONTAINER_LIMIT",
        "INSUFFICIENT_PAYLOAD_WITHIN_CONTAINER_LIMIT",
    }
    assert assessment.aggregate_lower_bound == 2
    assert assessment.volume_deficit_m3 > 0
    assert assessment.payload_deficit_kg == 8


def test_capacity_limit_precheck_pass_is_only_aggregate_evidence() -> None:
    inventory = normalize_container_inventory([
        _container("C1", side=10, payload=10),
        _container("C2", side=10, payload=10),
    ])
    items = [Item("A", 8, 8, 8, 5), Item("B", 8, 8, 8, 5)]

    assessment = assess_capacity_within_container_limit(items, inventory, 2)

    assert assessment.valid
    assert assessment.issues == ()
    assert assessment.metadata()["capacity_limit_precheck_valid"] is True


def test_strict_one_container_search_checks_catalog_not_input_prefix() -> None:
    containers = [
        _container("C_PREFIX_TOO_SMALL", side=5, cost=1),
        _container("C_EXPENSIVE", side=12, cost=20),
        _container("C_CHEAPEST_FEASIBLE", side=10, cost=10),
    ]
    policy = LazyRankedContainerSubsetPolicy(
        InventorySearchLimits(1, 1, False),
        exhaustive_max_containers=10,
    )

    candidates = list(policy.candidates(containers, [Item("I1", 9, 9, 9, 1)]))

    assert [value[0].container_id for value in candidates] == [
        "C_CHEAPEST_FEASIBLE", "C_EXPENSIVE",
    ]


def test_large_equivalent_inventory_yields_one_singleton_type_candidate() -> None:
    containers = [_container(f"C{index:03d}") for index in range(500)]
    policy = LazyRankedContainerSubsetPolicy(
        InventorySearchLimits(1, 1, False),
        exhaustive_max_containers=10,
    )

    candidates = list(policy.candidates(containers, [Item("I1", 1, 1, 1, 1)]))

    assert len(candidates) == 1
    assert candidates[0][0].container_id == "C000"
    assert policy.metadata()["inventory_equivalent_type_count"] == 1


def test_large_equivalent_inventory_deduplicates_physical_subsets_by_type_composition() -> None:
    containers = [_container(f"C{index:03d}") for index in range(500)]
    policy = LazyRankedContainerSubsetPolicy(
        InventorySearchLimits(9, 10, True),
        exhaustive_max_containers=10,
        max_candidates_per_count=64,
    )

    candidates = list(policy.candidates(
        containers,
        [Item("I1", 1, 1, 1, 1)],
    ))

    assert len(candidates) == 2
    assert [len(value) for value in candidates] == [9, 10]
    assert candidates[0][0].container_id == "C000"
    metadata = policy.metadata()
    assert metadata["container_type_compositions_generated"] == 2
    assert metadata["duplicate_physical_subsets_avoided"] > 0
    assert metadata["container_type_compositions_by_cardinality"] == {9: 1, 10: 1}


def test_large_inventory_schedules_one_capacity_anchor_for_each_cardinality_first() -> None:
    containers = [_container(f"C{index:03d}") for index in range(500)]
    policy = LazyRankedContainerSubsetPolicy(
        InventorySearchLimits(9, 15, True),
        exhaustive_max_containers=10,
    )

    candidates = list(policy.candidates(
        containers,
        [Item("I1", 1, 1, 1, 1)],
    ))

    assert [len(value) for value in candidates[:7]] == list(range(9, 16))
    assert policy.metadata()["container_subset_scheduling"] == (
        "capacity_anchor_each_cardinality_then_cost_portfolio"
    )


def test_acquisition_mode_yields_capacity_anchor_then_cost_candidate() -> None:
    containers = [
        *[
            _container(f"S{index:03d}", side=10, payload=10, cost=5)
            for index in range(20)
        ],
        *[
            _container(f"L{index:03d}", side=20, payload=20, cost=20)
            for index in range(20)
        ],
    ]
    policy = LazyRankedContainerSubsetPolicy(
        InventorySearchLimits(1, 1, False),
        exhaustive_max_containers=10,
        max_candidates_per_count=2,
        candidate_mode="incumbent_acquisition",
        cardinalities_override=(1,),
    )

    candidates = list(policy.candidates(
        containers, [Item("I1", 5, 5, 5, 1)],
    ))

    assert [value[0].container_id for value in candidates] == ["L000", "S000"]
    assert policy.metadata()["container_subset_candidates_generated"] == 2
    assert policy.metadata()["container_subset_scheduling"] == (
        "capacity_rich_then_cost_acquisition"
    )


def test_soft_volume_buffer_ranks_but_does_not_prune_tight_valid_subset() -> None:
    exact = _container("EXACT", side=10, cost=5)
    roomy = _container("ROOMY", side=11, cost=10)
    item = Item("I1", 10, 10, 10, 1)
    policy = LazyRankedContainerSubsetPolicy(
        InventorySearchLimits(1, 1, False),
        soft_volume_buffer_ratio=0.20,
    )

    candidates = list(policy.candidates([exact, roomy], [item]))

    assert [value[0].container_id for value in candidates] == ["EXACT", "ROOMY"]


def test_lazy_policy_stops_before_generation_when_deadline_has_passed() -> None:
    policy = LazyRankedContainerSubsetPolicy(
        InventorySearchLimits(1, 1, False),
        deadline_monotonic=perf_counter() - 1,
    )

    assert list(policy.candidates([_container("C1")], [Item("I1", 1, 1, 1, 1)])) == []
    assert policy.metadata()["container_subset_deadline_reached"] is True


def test_best_fit_can_search_the_catalog_instead_of_using_the_input_prefix() -> None:
    containers = [
        _container("C_PREFIX_TOO_SMALL", side=5, cost=1),
        _container("C_EXPENSIVE", side=12, cost=20),
        _container("C_CHEAPEST_FEASIBLE", side=10, cost=10),
    ]
    policy = LazyRankedContainerSubsetPolicy(
        InventorySearchLimits(1, 1, False),
        exhaustive_max_containers=10,
    )

    outcome = solve(
        [Item("I1", 9, 9, 9, 1)],
        containers,
        {"subset_enumeration_limit": 10},
        container_subset_policy=policy,
    )

    assert outcome.solve.status == "FEASIBLE"
    assert {value.container_id for value in outcome.placements} == {
        "C_CHEAPEST_FEASIBLE"
    }
    assert outcome.metadata["inventory_physical_container_count"] == 3
    assert (
        outcome.metadata["container_subset_capacity_pruned"]
        + outcome.metadata["container_subset_compatibility_pruned"]
    ) == 1
