from __future__ import annotations

from collections import Counter

from container_packing.algorithms.heuristics.container_subset_selection import (
    AdaptiveContainerSubsetSelectionPolicy,
)
from container_packing.schemas import Container, Item


def _containers(count: int) -> list[Container]:
    return [
        Container(
            f"C{index + 1}",
            1000 + index * 100,
            1000,
            1000,
            1000 + index * 100,
            100 + index * 10,
            volume_m3=1.0 + index * 0.1,
        )
        for index in range(count)
    ]


def test_adaptive_subset_policy_is_exhaustive_for_small_catalog() -> None:
    policy = AdaptiveContainerSubsetSelectionPolicy(
        exhaustive_max_containers=5,
        max_candidates_per_count=2,
    )
    candidates = policy.candidates(
        _containers(5), [Item("I1", 100, 100, 100, 10)]
    )
    pairs = {
        tuple(value.container_id for value in subset)
        for subset in candidates
        if len(subset) == 2
    }

    assert len(pairs) == 10
    assert ("C3", "C4") in pairs
    assert policy.metadata()["container_subset_search_mode"] == "exhaustive_small_catalog"


def test_adaptive_subset_policy_is_bounded_and_deterministic_for_large_catalog() -> None:
    items = [Item("I1", 100, 100, 100, 10)]
    first_policy = AdaptiveContainerSubsetSelectionPolicy(
        exhaustive_max_containers=5,
        max_candidates_per_count=4,
    )
    second_policy = AdaptiveContainerSubsetSelectionPolicy(
        exhaustive_max_containers=5,
        max_candidates_per_count=4,
    )
    first = first_policy.candidates(_containers(12), items)
    second = second_policy.candidates(_containers(12), items)

    assert [tuple(value.container_id for value in subset) for subset in first] == [
        tuple(value.container_id for value in subset) for subset in second
    ]
    assert max(Counter(map(len, first)).values()) <= 4
    assert first_policy.metadata()["container_subset_search_mode"] == "bounded_diverse_large_catalog"
