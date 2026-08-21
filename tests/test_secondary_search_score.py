from __future__ import annotations

import pytest
from scipy.optimize import OptimizeResult

from container_packing.algorithms.contracts import AlgorithmOutcome
from container_packing.algorithms.search import (
    ValidatedIncumbentStore,
    calculate_secondary_search_score,
)
from container_packing.algorithms.search.configuration import (
    SecondarySearchScoreConfiguration,
)
from container_packing.schemas import Container, Placement, SolveResult


def _container(container_id: str, *, cost: float = 10) -> Container:
    return Container(container_id, 10, 10, 10, 10, cost, volume_m3=1e-6)


def _placement(item_id: str, container_id: str, *, x: float) -> Placement:
    return Placement(item_id, container_id, x, 0, 0, 5, 10, 10, 5)


def _outcome(placement: Placement) -> AlgorithmOutcome:
    return AlgorithmOutcome(
        SolveResult("FEASIBLE", "test", 1.0, None, OptimizeResult()),
        [placement], "test", {},
    )


def test_secondary_score_is_normalized_and_deterministic() -> None:
    container = _container("C1")
    placement = _placement("I1", "C1", x=0)

    first = calculate_secondary_search_score(
        [placement], [container], support_threshold=0.8,
    )
    second = calculate_secondary_search_score(
        [placement], [container], support_threshold=0.8,
    )

    assert first == second
    assert first.as_dict()["utilization_concentration"] == pytest.approx(0.25)
    assert first.as_dict()["internal_void_ratio"] == pytest.approx(0.0)
    assert first.as_dict()["minimum_support_margin"] == pytest.approx(0.2)


def test_validated_incumbent_uses_secondary_score_only_for_official_ties() -> None:
    container = _container("C1")
    factory = lambda placements: calculate_secondary_search_score(
        placements, [container], support_threshold=None,
    )
    store = ValidatedIncumbentStore(
        required_item_ids=["I1"], containers=[container],
        validator=lambda placements: True, secondary_score_factory=factory,
    )

    assert store.consider(_outcome(_placement("I1", "C1", x=5)))
    assert store.consider(_outcome(_placement("I1", "C1", x=0)))
    assert store.outcome is not None
    assert store.outcome.placements[0].x_mm == 0
    assert store.metadata()["validated_incumbent_secondary_score"] is not None


def test_official_objective_always_dominates_secondary_score() -> None:
    cheap = _container("CHEAP", cost=1)
    expensive = _container("EXPENSIVE", cost=10)
    containers = [cheap, expensive]
    store = ValidatedIncumbentStore(
        required_item_ids=["I1"], containers=containers,
        validator=lambda placements: True,
        secondary_score_factory=lambda placements: calculate_secondary_search_score(
            placements, containers, support_threshold=None,
        ),
    )

    assert store.consider(_outcome(_placement("I1", "CHEAP", x=5)))
    assert not store.consider(_outcome(_placement("I1", "EXPENSIVE", x=0)))
    assert store.objective is not None
    assert store.objective.total_container_cost == 1


def test_secondary_search_score_policy_version_and_default_are_locked() -> None:
    disabled = SecondarySearchScoreConfiguration()
    enabled = SecondarySearchScoreConfiguration(enabled=True)

    assert disabled.enabled is False
    assert disabled.metadata()["secondary_search_score_policy"] == "disabled"
    assert enabled.metadata()["secondary_search_score_policy"] == (
        "utilization_void_support_margin_v1"
    )
