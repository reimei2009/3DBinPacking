"""Optional candidate-point extension point for Extreme-Point constructors."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from ...geometry.orientation import OrientedDimensions
from ...schemas import Item
if TYPE_CHECKING:
    from .extreme_point_core import ContainerState

Point = tuple[float, float, float]


class CandidatePointProvider(Protocol):
    """Provide deterministic extra candidate origins for one item orientation."""

    def points(
        self, state: "ContainerState", item: Item, dimensions: OrientedDimensions
    ) -> tuple[Point, ...]: ...

    def metadata(self) -> dict[str, object]: ...
