"""Delivery-aware candidate extensions for the Level 8 Best Fit A/B fixture."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..algorithms.feasibility import PlacementFeasibilityPolicy
from ..algorithms.heuristics.candidate_points import CandidatePointProvider
from ..algorithms.heuristics.candidate_scoring import CandidateScoringPolicy
from ..algorithms.heuristics.extreme_point_core import ContainerState
from ..algorithms.heuristics.first_fit_selection import FirstFitCandidate, FirstFitCandidateSelectionPolicy
from ..geometry.orientation import OrientedDimensions
from ..schemas import Container, Item, Placement
from .center_of_mass import evaluate_center_of_mass
from .level_07_balance_points import BalanceAnchorPointProvider
from .unloading import UnloadingSettings, prospective_direct_rehandle_delta
from ..geometry.support import evaluate_support


@dataclass
class StrictLifoFeasibilityPolicy:
    """Compose inherited feasibility with strict static LIFO.

    The policy rejects only candidate-created later-priority blockers. Existing
    pairs were already accepted by the same policy, so this incremental check
    is equivalent to revalidating the full container after every placement.
    """

    items_by_id: dict[str, Item]
    settings: UnloadingSettings
    base: PlacementFeasibilityPolicy
    policy_id: str = (
        "level_08_compound_geometry_payload_support_stackability_load_bearing_"
        "strict_lifo"
    )
    lifo_candidates_evaluated: int = 0
    lifo_rejected_candidates: int = 0
    lifo_valid_candidates: int = 0
    lifo_rejection_examples: list[str] = field(default_factory=list)

    def allows(
        self,
        container: Container,
        existing: list[Placement],
        candidate: Placement,
        *,
        loaded_weight_kg: float,
        tolerance: float,
    ) -> bool:
        if not self.base.allows(
            container,
            existing,
            candidate,
            loaded_weight_kg=loaded_weight_kg,
            tolerance=tolerance,
        ):
            return False
        self.lifo_candidates_evaluated += 1
        _, later_blockers = prospective_direct_rehandle_delta(
            self.items_by_id,
            existing,
            candidate,
            self.settings,
            tolerance_mm=tolerance,
        )
        if later_blockers:
            self.lifo_rejected_candidates += 1
            if len(self.lifo_rejection_examples) < 10:
                self.lifo_rejection_examples.append(
                    f"{candidate.item_id}@{candidate.container_id}:"
                    f"({candidate.x_mm},{candidate.y_mm},{candidate.z_mm})"
                )
            return False
        self.lifo_valid_candidates += 1
        return True

    def metadata(self) -> dict[str, object]:
        return {
            **self.base.metadata(),
            "feasibility_policy": self.policy_id,
            "strict_lifo_candidate_feasibility_enabled": True,
            "strict_lifo_candidates_evaluated": self.lifo_candidates_evaluated,
            "strict_lifo_rejected_candidates": self.lifo_rejected_candidates,
            "strict_lifo_valid_candidates": self.lifo_valid_candidates,
            "strict_lifo_rejection_examples": list(self.lifo_rejection_examples),
        }


@dataclass
class DeliveryDependencyFeasibilityPolicy:
    """Reject support edges that contradict declared delivery precedence.

    If candidate ``i`` rests on existing item ``j``, unloading requires
    ``i`` before ``j``. Since smaller priority means earlier delivery, the
    necessary relation is ``priority(i) <= priority(j)``. This incremental
    gate prevents a packing that is static-LIFO valid but impossible to replay
    without removing a later-stop item first.
    """

    items_by_id: dict[str, Item]
    base: PlacementFeasibilityPolicy
    support_epsilon_mm: float = 1e-4
    policy_id: str = "level_08_delivery_priority_support_dependency_v1"
    candidates_evaluated: int = 0
    rejected_candidates: int = 0
    valid_candidates: int = 0
    rejection_examples: list[str] = field(default_factory=list)

    def allows(
        self,
        container: Container,
        existing: list[Placement],
        candidate: Placement,
        *,
        loaded_weight_kg: float,
        tolerance: float,
    ) -> bool:
        if not self.base.allows(
            container,
            existing,
            candidate,
            loaded_weight_kg=loaded_weight_kg,
            tolerance=tolerance,
        ):
            return False
        self.candidates_evaluated += 1
        candidate_priority = int(
            str(self.items_by_id[candidate.item_id].source["delivery_priority"])
        )
        support = evaluate_support(
            candidate, existing, epsilon_mm=self.support_epsilon_mm
        )
        conflicting = tuple(
            supporter_id
            for supporter_id in support.supporting_item_ids
            if candidate_priority
            > int(
                str(
                    self.items_by_id[supporter_id].source["delivery_priority"]
                )
            )
        )
        if conflicting:
            self.rejected_candidates += 1
            if len(self.rejection_examples) < 10:
                self.rejection_examples.append(
                    f"{candidate.item_id}@{candidate.container_id} supported_by="
                    + ",".join(conflicting)
                )
            return False
        self.valid_candidates += 1
        return True

    def metadata(self) -> dict[str, object]:
        return {
            **self.base.metadata(),
            "feasibility_policy": self.policy_id,
            "delivery_dependency_candidates_evaluated": self.candidates_evaluated,
            "delivery_dependency_rejected_candidates": self.rejected_candidates,
            "delivery_dependency_valid_candidates": self.valid_candidates,
            "delivery_dependency_rejection_examples": list(
                self.rejection_examples
            ),
        }


@dataclass
class SequentialBalanceFeasibilityPolicy:
    """Require every reverse-loading state to satisfy the Level 7 COG band.

    Delivery-first construction places later stops before earlier stops.
    Therefore every accepted partial packing is a cargo state that can appear
    while unloading in reverse. Requiring prospective COG validity here gives
    the sequential planner a known balance-safe removal path without changing
    the Level 7 thresholds.
    """

    balance_config: dict
    base: PlacementFeasibilityPolicy
    policy_id: str = "level_08_reverse_loading_state_balance_hard_gate_v1"
    candidates_evaluated: int = 0
    rejected_candidates: int = 0
    valid_candidates: int = 0

    def allows(
        self,
        container: Container,
        existing: list[Placement],
        candidate: Placement,
        *,
        loaded_weight_kg: float,
        tolerance: float,
    ) -> bool:
        if not self.base.allows(
            container,
            existing,
            candidate,
            loaded_weight_kg=loaded_weight_kg,
            tolerance=tolerance,
        ):
            return False
        self.candidates_evaluated += 1
        record = evaluate_center_of_mass(
            [*existing, candidate],
            [container],
            self.balance_config,
            tolerance=tolerance,
        ).records[0]
        if not record.balanced:
            self.rejected_candidates += 1
            return False
        self.valid_candidates += 1
        return True

    def metadata(self) -> dict[str, object]:
        return {
            **self.base.metadata(),
            "feasibility_policy": self.policy_id,
            "sequential_balance_construction_enabled": True,
            "sequential_balance_construction_mode": (
                "hard_every_reverse_loading_state_v1"
            ),
            "sequential_balance_candidates_evaluated": self.candidates_evaluated,
            "sequential_balance_rejected_candidates": self.rejected_candidates,
            "sequential_balance_valid_candidates": self.valid_candidates,
        }


@dataclass(frozen=True)
class DeliveryDoorPointProvider(CandidatePointProvider):
    """Offer a far-from-door anchor so later-delivery items need not occupy x=0."""

    settings: UnloadingSettings
    balance_config: dict | None = None
    policy_id: str = "level_08_door_aware_candidate_points_v1"

    def points(
        self, state: ContainerState, item: Item, dimensions: OrientedDimensions
    ) -> tuple[tuple[float, float, float], ...]:
        points = set(state.extreme_points)
        if self.balance_config is not None:
            points.update(
                BalanceAnchorPointProvider(self.balance_config).points(
                    state, item, dimensions
                )
            )
        if self.settings.door_face == "x_min":
            points.add((state.container.length_mm - dimensions.length_mm, 0.0, 0.0))
            points.update(
                (placement.x_mm - dimensions.length_mm, placement.y_mm, placement.z_mm)
                for placement in state.placements
                if placement.x_mm >= dimensions.length_mm
            )
            # Extreme-point geometry normally exposes a support surface from
            # its near-side corner. Add the corresponding far-side corner so
            # later-stop items can be constructed behind earlier-stop items
            # while retaining exact support.
            points.update(
                (
                    placement.x_mm + placement.length_mm - dimensions.length_mm,
                    placement.y_mm,
                    placement.z_mm + placement.height_mm,
                )
                for placement in state.placements
                if placement.length_mm >= dimensions.length_mm
            )
        elif self.settings.door_face == "x_max":
            points.add((0.0, 0.0, 0.0))
            points.update(
                (placement.x_mm, placement.y_mm, placement.z_mm + placement.height_mm)
                for placement in state.placements
            )
        return tuple(sorted(points, key=lambda value: (value[2], value[1], value[0])))

    def metadata(self) -> dict[str, object]:
        return {
            "candidate_point_provider": self.policy_id,
            "delivery_candidate_point_modes": [
                "far_door_anchor", "front_contact_anchor",
                "support_surface_far_anchor",
                *(
                    ["level_07_cog_target_anchor"]
                    if self.balance_config is not None
                    else []
                ),
            ],
        }


@dataclass
class DeliveryAwareCandidateScoringPolicy(CandidateScoringPolicy):
    """Use candidate-only LIFO deltas without changing feasibility."""

    items_by_id: dict[str, Item]
    settings: UnloadingSettings
    balance_config: dict | None = None
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
        same_priority_count = self._same_priority_count(candidate_item, state)
        balance_score = self._balance_score(state, candidate)
        # Preserve container-count/cost priority. Delivery criteria only refine
        # the candidate geometry tie-break after those objectives.
        return base_score[:2] + balance_score + (
            float(direct_rehandles), float(later_blockers), future_risk,
            float(same_priority_count),
        ) + base_score[2:]

    def _balance_score(
        self, state: ContainerState, candidate: Placement
    ) -> tuple[float, ...]:
        if self.balance_config is None:
            return ()
        record = evaluate_center_of_mass(
            [*state.placements, candidate],
            [state.container],
            self.balance_config,
        ).records[0]
        violation = max(
            0.0,
            record.absolute_longitudinal_offset_ratio
            - record.max_longitudinal_offset_ratio,
        ) + max(
            0.0,
            record.absolute_lateral_offset_ratio
            - record.max_lateral_offset_ratio,
        )
        return (
            violation,
            record.absolute_longitudinal_offset_ratio
            + record.absolute_lateral_offset_ratio,
        )

    def _same_priority_count(self, item: Item, state: ContainerState) -> int:
        priority = int(str(item.source["delivery_priority"]))
        return sum(
            int(str(self.items_by_id[value.item_id].source["delivery_priority"]))
            == priority
            for value in state.placements
        )

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
            "delivery_priority_spread_tiebreak": "same_priority_count_per_open_container",
            "delivery_balance_scoring_enabled": self.balance_config is not None,
        }


@dataclass
class DeliveryAwareFirstFitCandidateSelection(FirstFitCandidateSelectionPolicy):
    """Rank positions only inside FFD's first container that has a candidate."""

    items_by_id: dict[str, Item]
    settings: UnloadingSettings
    balance_config: dict | None = None
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
                *self._balance_score(state, candidate.placement),
                float(direct_rehandles),
                float(later_blockers),
                self._future_blocker_risk(item, candidate.placement, state),
                *candidate.original_rank,
            )

        return min(candidates, key=rank).placement

    def _balance_score(
        self, state: ContainerState, candidate: Placement
    ) -> tuple[float, ...]:
        if self.balance_config is None:
            return ()
        record = evaluate_center_of_mass(
            [*state.placements, candidate],
            [state.container],
            self.balance_config,
        ).records[0]
        return (
            max(
                0.0,
                record.absolute_longitudinal_offset_ratio
                - record.max_longitudinal_offset_ratio,
            )
            + max(
                0.0,
                record.absolute_lateral_offset_ratio
                - record.max_lateral_offset_ratio,
            ),
            record.absolute_longitudinal_offset_ratio
            + record.absolute_lateral_offset_ratio,
        )

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
            "delivery_balance_scoring_enabled": self.balance_config is not None,
        }
