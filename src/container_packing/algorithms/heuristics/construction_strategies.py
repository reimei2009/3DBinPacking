"""Reusable construction and repair strategies for local/metaheuristic search."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..contracts import AlgorithmOutcome
from ..feasibility import PlacementFeasibilityPolicy
from ..orientation import OrientationProvider
from ...schemas import Container, Item, Placement
from .extreme_point_best_fit import pack_order_best_fit, solve as solve_extreme_point_best_fit
from .extreme_point_core import SearchStats, pack_order_first_fit
from .extreme_point_ffd import solve as solve_extreme_point_ffd


RepairPackOrder = Callable[
    [list[Item], tuple[Container, ...], float, SearchStats, PlacementFeasibilityPolicy],
    list[Placement] | None,
]


@dataclass(frozen=True)
class ConstructionStrategy:
    """One compatible initial-construction and destroy-and-repair policy."""

    strategy_id: str
    solve_initial: Callable[..., AlgorithmOutcome]
    pack_repair_order: Callable[..., list[Placement] | None]

    def initial(
        self,
        items: list[Item],
        containers: list[Container],
        settings: dict,
        *,
        policy: PlacementFeasibilityPolicy,
        orientation_provider: OrientationProvider,
    ) -> AlgorithmOutcome:
        return self.solve_initial(
            items, containers, settings,
            policy=policy, orientation_provider=orientation_provider,
        )

    def repair(
        self,
        items: list[Item],
        containers: tuple[Container, ...],
        tolerance: float,
        stats: SearchStats,
        policy: PlacementFeasibilityPolicy,
        *,
        orientation_provider: OrientationProvider,
    ) -> list[Placement] | None:
        return self.pack_repair_order(
            items, containers, tolerance, stats, policy,
            orientation_provider=orientation_provider,
        )


_STRATEGIES = {
    "extreme_point_ffd": ConstructionStrategy(
        "extreme_point_ffd", solve_extreme_point_ffd, pack_order_first_fit,
    ),
    "extreme_point_best_fit": ConstructionStrategy(
        "extreme_point_best_fit", solve_extreme_point_best_fit, pack_order_best_fit,
    ),
}


def get_construction_strategy(strategy_id: str) -> ConstructionStrategy:
    """Return a registered strategy or raise an actionable configuration error."""
    try:
        return _STRATEGIES[strategy_id]
    except KeyError as exc:
        available = ", ".join(sorted(_STRATEGIES))
        raise ValueError(
            f"Unknown construction strategy {strategy_id!r}; available: {available}"
        ) from exc
