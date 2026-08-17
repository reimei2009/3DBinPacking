from __future__ import annotations

import pytest

from container_packing.geometry.contact_index import (
    ContactSupportIndex,
    ContactSupportIndexStats,
    PlacementFeasibilityContext,
)
from container_packing.geometry.support import evaluate_support
from container_packing.data_loader import load_config
from container_packing.levels.level_04_algorithms import execute_level_04
from container_packing.levels.level_05_algorithms import execute_level_05
from container_packing.levels.load_bearing import LoadBearingAttributes
from container_packing.levels.load_transfer import evaluate_load_transfer
from container_packing.levels.stackability import (
    StackabilityAttributes,
    infer_parent_relations,
)
from container_packing.schemas import Container, Item, Placement


def _placement(
    item_id: str, x: float, y: float, z: float,
    length: float, width: float, height: float = 5,
) -> Placement:
    return Placement(item_id, "C", x, y, z, length, width, height, 1)


def test_index_matches_brute_force_for_multi_support_epsilon_and_edge_contact() -> None:
    left = _placement("LEFT", 0, 0, 0, 5, 10)
    right = _placement("RIGHT", 5, 0, 0, 5, 10)
    wrong_height = _placement("LOW", 0, 0, 1, 10, 10, 3)
    edge_only = _placement("EDGE", 10, 0, 0, 2, 10)
    rotated_shape = _placement("ROTATED", 2, 2, 9, 8, 3, 1)
    child = _placement("TOP", 0, 0, 5 + 5e-5, 10, 10)
    placements = [right, wrong_height, edge_only, left, rotated_shape]
    stats = ContactSupportIndexStats()
    index = ContactSupportIndex(placements, stats=stats)

    indexed = index.supporters(child, epsilon_mm=1e-4)
    brute = evaluate_support(child, placements, epsilon_mm=1e-4)
    measured = evaluate_support(child, indexed, epsilon_mm=1e-4)

    assert tuple(value.item_id for value in indexed) == ("LEFT", "RIGHT")
    assert measured.supporting_item_ids == brute.supporting_item_ids
    assert measured.support_area_mm2 == pytest.approx(brute.support_area_mm2)
    assert measured.exact_support_ratio == pytest.approx(brute.exact_support_ratio)
    assert measured.center_supported == brute.center_supported
    assert stats.queries == 1
    assert stats.placements_examined == 2
    assert stats.estimated_scans_avoided == 3


def test_seed_rebuild_and_projected_candidate_are_queryable_without_mutation() -> None:
    floor = _placement("FLOOR", 0, 0, 0, 10, 10)
    projected = _placement("PROJECTED", 0, 0, 5, 10, 10)
    top = _placement("TOP", 0, 0, 10, 10, 10)
    index = ContactSupportIndex([floor])
    context = PlacementFeasibilityContext(index, (projected,))

    assert tuple(value.item_id for value in context.supporters(
        projected, epsilon_mm=1e-4,
    )) == ("FLOOR",)
    assert tuple(value.item_id for value in context.supporters(
        top, epsilon_mm=1e-4,
    )) == ("PROJECTED",)
    assert index.placement_count == 1


def test_candidate_context_memoizes_supporters_without_leaking_to_next_candidate() -> None:
    floor = _placement("FLOOR", 0, 0, 0, 10, 10)
    first = _placement("FIRST", 0, 0, 5, 10, 10)
    second = _placement("SECOND", 0, 0, 5, 5, 10)
    stats = ContactSupportIndexStats()
    index = ContactSupportIndex([floor], stats=stats)
    first_context = PlacementFeasibilityContext(index, (first,))

    expected = first_context.supporters(first, epsilon_mm=1e-4)
    assert first_context.supporters(first, epsilon_mm=1e-4) == expected
    assert stats.cache_misses == 1
    assert stats.cache_hits == 1
    assert stats.queries == 1

    second_context = PlacementFeasibilityContext(index, (second,))
    assert tuple(value.item_id for value in second_context.supporters(
        second, epsilon_mm=1e-4,
    )) == ("FLOOR",)
    assert stats.cache_misses == 2
    assert stats.cache_hits == 1
    assert stats.queries == 2


def test_context_cache_is_invalidated_by_new_commit_and_rebuild() -> None:
    floor = _placement("FLOOR", 0, 0, 0, 10, 10)
    child = _placement("CHILD", 0, 0, 5, 10, 10)
    index = ContactSupportIndex()
    before_commit = PlacementFeasibilityContext(index)
    assert before_commit.supporters(child, epsilon_mm=1e-4) == ()

    index.add(floor)
    after_commit = PlacementFeasibilityContext(index)
    assert tuple(value.item_id for value in after_commit.supporters(
        child, epsilon_mm=1e-4,
    )) == ("FLOOR",)

    rebuilt = ContactSupportIndex([floor])
    rebuilt_context = PlacementFeasibilityContext(rebuilt)
    assert rebuilt_context.supporters(child, epsilon_mm=1e-4) == (
        floor,
    )


def test_stack_parent_and_load_transfer_match_brute_force() -> None:
    bottom = _placement("BOTTOM", 0, 0, 0, 10, 10)
    top = _placement("TOP", 0, 0, 5, 10, 10)
    placements = [bottom, top]
    index = ContactSupportIndex(placements)
    stack_attributes = {
        item_id: StackabilityAttributes("G", False, 3, "test")
        for item_id in ("BOTTOM", "TOP")
    }
    load_attributes = {
        item_id: LoadBearingAttributes(item_id, 100, False, "test")
        for item_id in ("BOTTOM", "TOP")
    }
    lookup = lambda child: index.supporters(child, epsilon_mm=1e-4)

    assert infer_parent_relations(
        placements, stack_attributes, epsilon_mm=1e-4,
    ) == infer_parent_relations(
        placements, stack_attributes, epsilon_mm=1e-4,
        supporter_lookup=lookup,
    )
    assert evaluate_load_transfer(
        placements, load_attributes, epsilon_mm=1e-4,
    ) == evaluate_load_transfer(
        placements, load_attributes, epsilon_mm=1e-4,
        supporter_lookup=lookup,
    )


@pytest.mark.parametrize(
    "executor,algorithm_id", [
        (execute_level_04, "extreme_point_best_fit"),
        (execute_level_04, "extreme_point_ffd"),
        (execute_level_04, "maximal_space_best_fit"),
        (execute_level_05, "extreme_point_best_fit"),
        (execute_level_05, "extreme_point_ffd"),
        (execute_level_05, "maximal_space_best_fit"),
    ],
)
def test_constructor_result_and_rejection_counters_match_with_index(
    root, executor, algorithm_id,
) -> None:
    items = [
        Item(
            item_id, 10, 10, 5, 1,
            source={"stackability_code": "1", "max_stackability": "3"},
        )
        for item_id in ("A", "B")
    ]
    containers = [Container("C", 10, 10, 10, 100, 1)]
    common = {
        "subset_enumeration_limit": 4,
        "support": {"threshold": 1.0, "epsilon_mm": 1e-4},
        "stackability": load_config(root / "config/level_04/stackability_rules.yaml"),
        "load_bearing": load_config(root / "config/level_05/load_bearing_rules.yaml"),
        "validation": {"load_tolerance_kg": 1e-6},
    }
    disabled = executor(
        algorithm_id, items, containers,
        {**common, "contact_support_index": {"enabled": False}},
    )
    enabled = executor(
        algorithm_id, items, containers,
        {**common, "contact_support_index": {"enabled": True}},
    )

    assert enabled.solve.status == disabled.solve.status == "FEASIBLE"
    assert enabled.solve.objective_value == disabled.solve.objective_value
    assert enabled.placements == disabled.placements
    for counter in (
        "geometry_rejected_candidates", "support_rejected_candidates",
        "stackability_rejected_candidates", "load_bearing_rejected_candidates",
    ):
        assert enabled.metadata.get(counter) == disabled.metadata.get(counter)
    assert enabled.metadata["contact_support_index_enabled"] is True
    assert enabled.metadata["contact_support_index_queries"] > 0
    assert enabled.metadata["contact_support_index_cache_hits"] > 0
    assert enabled.metadata["contact_support_index_cache_misses"] > 0
    assert enabled.metadata["contact_support_index_exact_contact_checks"] > 0
    assert enabled.metadata["contact_support_index_query_runtime_seconds"] > 0
    assert disabled.metadata["contact_support_index_enabled"] is False
