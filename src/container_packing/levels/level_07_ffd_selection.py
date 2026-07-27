"""Level 7 COG tie-break within the first feasible FFD container."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..algorithms.heuristics.first_fit_selection import FirstFitCandidate, FirstFitCandidateSelectionPolicy
from ..algorithms.heuristics.extreme_point_core import ContainerState
from ..schemas import Placement
from .center_of_mass import evaluate_center_of_mass


@dataclass
class BalanceAwareFirstFitCandidateSelection(FirstFitCandidateSelectionPolicy):
    balance_config: dict[str, Any]
    policy_id: str = "level_07_first_feasible_container_prospective_cog_tiebreak_v1"
    candidates_scored: int = 0

    def select(self, state: ContainerState, candidates: tuple[FirstFitCandidate, ...]) -> Placement:
        self.candidates_scored += len(candidates)

        def rank(candidate: FirstFitCandidate) -> tuple[float, ...]:
            record = evaluate_center_of_mass(
                [*state.placements, candidate.placement], [state.container], self.balance_config
            ).records[0]
            violation = max(0.0, record.absolute_longitudinal_offset_ratio - record.max_longitudinal_offset_ratio)
            violation += max(0.0, record.absolute_lateral_offset_ratio - record.max_lateral_offset_ratio)
            offset = record.absolute_longitudinal_offset_ratio + record.absolute_lateral_offset_ratio
            return violation, offset, *candidate.original_rank

        return min(candidates, key=rank).placement

    def metadata(self) -> dict[str, object]:
        return {
            "first_fit_candidate_selection_policy": self.policy_id,
            "balance_scored_candidates": self.candidates_scored,
            "balance_construction_mode": "first_feasible_container_soft_tiebreak_final_validation_hard",
        }
