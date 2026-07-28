"""Optional intra-container selection hooks for Extreme-Point First Fit."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from ...schemas import Placement

if TYPE_CHECKING:
    from .extreme_point_core import ContainerState


@dataclass(frozen=True)
class FirstFitCandidate:
    placement: Placement
    original_rank: tuple[float, float, float, int]


class FirstFitCandidateSelectionPolicy(Protocol):
    """Choose among feasible candidates in the first feasible container only."""

    policy_id: str

    def select(self, state: "ContainerState", candidates: tuple[FirstFitCandidate, ...]) -> Placement: ...

    def metadata(self) -> dict[str, object]: ...
