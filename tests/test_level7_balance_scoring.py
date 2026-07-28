from __future__ import annotations

from pathlib import Path

from container_packing.algorithms.heuristics.extreme_point_best_fit import best_fit_candidate_score
from container_packing.algorithms.heuristics.extreme_point_core import ContainerState
from container_packing.data_loader import load_config
from container_packing.levels.level_07_balance_scoring import BalanceAwareCandidateScoringPolicy
from container_packing.schemas import Container, Placement


def _container(identifier: str = "C1") -> Container:
    return Container(identifier, 400, 200, 250, 500, 100, volume_m3=0.02)


def _placement(identifier: str, x: float, weight: float = 100.0) -> Placement:
    return Placement(identifier, "C1", x, 0, 100, 200, 200, 50, weight)


def test_balance_score_prefers_right_top_for_left_heavy_base(root: Path) -> None:
    rules = load_config(root / "config/level_07/balance_rules.yaml")
    state = ContainerState(_container())
    state.placements.extend([
        Placement("BASE-LEFT", "C1", 0, 0, 0, 200, 200, 100, 200),
        Placement("BASE-RIGHT", "C1", 200, 0, 0, 200, 200, 100, 50),
    ])
    policy = BalanceAwareCandidateScoringPolicy(rules)
    left = _placement("TOP", 0)
    right = _placement("TOP", 200)
    left_score = policy.score(state, left, 0, best_fit_candidate_score(state, left, 0))
    right_score = policy.score(state, right, 0, best_fit_candidate_score(state, right, 0))
    assert right_score < left_score
    assert left_score[2] > 0.0
    assert right_score[2] == 0.0


def test_balance_score_handles_empty_and_separate_container_states(root: Path) -> None:
    rules = load_config(root / "config/level_07/balance_rules.yaml")
    policy = BalanceAwareCandidateScoringPolicy(rules)
    empty = ContainerState(_container())
    candidate = Placement("A", "C1", 100, 0, 0, 200, 200, 50, 50)
    score = policy.score(empty, candidate, 0, best_fit_candidate_score(empty, candidate, 0))
    assert len(score) == len(best_fit_candidate_score(empty, candidate, 0)) + 2
    other = ContainerState(_container("C2"))
    other_candidate = Placement("B", "C2", 100, 0, 0, 200, 200, 50, 50)
    assert policy.score(other, other_candidate, 1, best_fit_candidate_score(other, other_candidate, 1))
    assert policy.metadata()["balance_scored_candidates"] == 2
