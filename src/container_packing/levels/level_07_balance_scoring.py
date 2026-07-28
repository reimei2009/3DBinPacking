"""Soft prospective center-of-mass score for Level 7 construction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..algorithms.heuristics.candidate_scoring import CandidateScoringPolicy
from ..algorithms.heuristics.extreme_point_core import ContainerState
from ..schemas import Placement
from .center_of_mass import evaluate_center_of_mass


@dataclass
class BalanceAwareCandidateScoringPolicy(CandidateScoringPolicy):
    """Guide placement toward balance; never reject a partial placement."""

    balance_config: dict[str, Any]
    policy_id: str = "level_07_prospective_center_of_mass_tiebreak_v1"
    candidates_scored: int = 0

    def score(
        self, state: ContainerState, candidate: Placement, container_rank: int,
        base_score: tuple[float, ...],
    ) -> tuple[float, ...]:
        del container_rank
        self.candidates_scored += 1
        record = evaluate_center_of_mass(
            [*state.placements, candidate], [state.container], self.balance_config
        ).records[0]
        violation = max(0.0, record.absolute_longitudinal_offset_ratio - record.max_longitudinal_offset_ratio)
        violation += max(0.0, record.absolute_lateral_offset_ratio - record.max_lateral_offset_ratio)
        target_offset = record.absolute_longitudinal_offset_ratio + record.absolute_lateral_offset_ratio
        # Preserve open-container and cost priority; balance precedes only geometric tie-breaks.
        return base_score[:2] + (violation, target_offset) + base_score[2:]

    def metadata(self) -> dict[str, object]:
        return {
            "candidate_scoring_policy": self.policy_id,
            "balance_scored_candidates": self.candidates_scored,
            "balance_construction_mode": "soft_tiebreak_final_validation_hard",
        }
