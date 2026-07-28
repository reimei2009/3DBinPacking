"""Delivery-aware candidate extensions for the Level 8 Best Fit A/B fixture."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..algorithms.heuristics.candidate_points import CandidatePointProvider
from ..algorithms.heuristics.candidate_scoring import CandidateScoringPolicy
from ..algorithms.heuristics.extreme_point_core import ContainerState
from ..algorithms.heuristics.first_fit_selection import FirstFitCandidate, FirstFitCandidateSelectionPolicy
from ..geometry.orientation import OrientedDimensions
from ..schemas import Item, Placement
from .unloading import UnloadingSettings, prospective_direct_rehandle_delta


@dataclass(frozen=True)
class DeliveryDoorPointProvider(CandidatePointProvider):
    """Offer a far-from-door anchor so later-delivery items need not occupy x=0."""

    settings: UnloadingSettings
    policy_id: str = "level_08_door_aware_candidate_points_v1"

    def points(
        self, state: ContainerState, item: Item, dimensions: OrientedDimensions
    ) -> tuple[tuple[float, float, float], ...]:
        del item
        points = set(state.extreme_points)
        if self.settings.door_face == "x_min":
            points.add((state.container.length_mm - dimensions.length_mm, 0.0, 0.0))
            points.update(
                (placement.x_mm - dimensions.length_mm, placement.y_mm, placement.z_mm)
                for placement in state.placements
                if placement.x_mm >= dimensions.length_mm
            )
        elif self.settings.door_face == "x_max":
            points.add((0.0, 0.0, 0.0))
        return tuple(sorted(points, key=lambda value: (value[2], value[1], value[0])))

    def metadata(self) -> dict[str, object]:
        return {
            "candidate_point_provider": self.policy_id,
            "delivery_candidate_point_modes": ["far_door_anchor", "front_contact_anchor"],
        }


@dataclass
class DeliveryAwareCandidateScoringPolicy(CandidateScoringPolicy):
    """Use candidate-only LIFO deltas without changing feasibility."""

    items_by_id: dict[str, Item]
    settings: UnloadingSettings
    policy_id: str = "level_08_prospective_direct_rehandle_tiebreak_v1"
    candidates_scored: int = 0

    def score(
        self, state: ContainerState, candidate: Placement, container_rank: int,
        base_score: tuple[float, ...],
    ) -> tuple[float, ...]:
        del container_rank
        self.candidates_scored += 1
        direct_rehandles, later_blockers = prospective_direct_rehandle_delta(
            self.items_by_id, state.placements, candidate, self.settings
        )
        candidate_item = self.items_by_id[candidate.item_id]
        future_risk = self._future_blocker_risk(candidate_item, candidate, state)
        # Preserve container-count/cost priority. Delivery criteria only refine
        # the candidate geometry tie-break after those objectives.
        return base_score[:2] + (
            float(direct_rehandles), float(later_blockers), future_risk,
        ) + base_score[2:]

    def _future_blocker_risk(
        self, item: Item, candidate: Placement, state: ContainerState
    ) -> float:
        priority = int(str(item.source["delivery_priority"]))
        minimum = min(int(str(value.source["delivery_priority"])) for value in self.items_by_id.values())
        if priority <= minimum:
            return 0.0
        if self.settings.door_face == "x_min":
            available = max(1.0, state.container.length_mm - candidate.length_mm)
            proximity = 1.0 - candidate.x_mm / available
        else:
            proximity = 0.0
        return float(priority - minimum) * max(0.0, proximity)

    def metadata(self) -> dict[str, object]:
        return {
            "candidate_scoring_policy": self.policy_id,
            "delivery_scored_candidates": self.candidates_scored,
            "delivery_construction_mode": "prospective_direct_rehandle_delta_then_future_blocker_tiebreak",
        }


@dataclass
class DeliveryAwareFirstFitCandidateSelection(FirstFitCandidateSelectionPolicy):
    """Rank positions only inside FFD's first container that has a candidate."""

    items_by_id: dict[str, Item]
    settings: UnloadingSettings
    policy_id: str = "level_08_first_feasible_container_delivery_lifo_tiebreak_v1"
    candidates_scored: int = 0

    def select(self, state: ContainerState, candidates: tuple[FirstFitCandidate, ...]) -> Placement:
        self.candidates_scored += len(candidates)

        def rank(candidate: FirstFitCandidate) -> tuple[float, ...]:
            direct_rehandles, later_blockers = prospective_direct_rehandle_delta(
                self.items_by_id, state.placements, candidate.placement, self.settings
            )
            item = self.items_by_id[candidate.placement.item_id]
            return (
                float(direct_rehandles),
                float(later_blockers),
                self._future_blocker_risk(item, candidate.placement, state),
                *candidate.original_rank,
            )

        return min(candidates, key=rank).placement

    def _future_blocker_risk(self, item: Item, candidate: Placement, state: ContainerState) -> float:
        priority = int(str(item.source["delivery_priority"]))
        minimum = min(int(str(value.source["delivery_priority"])) for value in self.items_by_id.values())
        if priority <= minimum or self.settings.door_face != "x_min":
            return 0.0
        available = max(1.0, state.container.length_mm - candidate.length_mm)
        proximity = 1.0 - candidate.x_mm / available
        return float(priority - minimum) * max(0.0, proximity)

    def metadata(self) -> dict[str, object]:
        return {
            "first_fit_candidate_selection_policy": self.policy_id,
            "delivery_scored_candidates": self.candidates_scored,
            "delivery_construction_mode": "first_feasible_container_prospective_direct_rehandle_delta_tiebreak",
            "delivery_container_selection_scope": "first_feasible_container_only",
        }
