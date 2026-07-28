"""Optional candidate-score extensions for constructive heuristics."""

from __future__ import annotations

from typing import Protocol

from ...schemas import Placement
from .extreme_point_core import ContainerState


class CandidateScoringPolicy(Protocol):
    """Refine an existing score without changing feasibility."""

    policy_id: str

    def score(
        self, state: ContainerState, candidate: Placement, container_rank: int,
        base_score: tuple[float, ...],
    ) -> tuple[float, ...]: ...

    def metadata(self) -> dict[str, object]: ...
