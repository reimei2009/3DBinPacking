"""Level 3 dispatch: horizontal orientation with exact geometric support."""

from __future__ import annotations

from typing import Any

from ..algorithms.feasibility import ExactSupportFeasibilityPolicy
from ..algorithms.heuristics.extreme_point_ffd import solve as solve_extreme_point_ffd
from ..algorithms.orientation import horizontal_orientation_provider
from ..schemas import Container, Item


def execute_level_03(
    algorithm_id: str, items: list[Item], containers: list[Container], settings: dict[str, Any]
):
    if algorithm_id != "extreme_point_ffd":
        raise ValueError(
            "Level 3 currently implements only 'extreme_point_ffd'; "
            "MILP and other heuristics are not enabled for horizontal orientation yet."
        )
    support = settings.get("support", {})
    policy = ExactSupportFeasibilityPolicy(
        threshold=float(support.get("threshold", 0.8)),
        epsilon_mm=float(support.get("epsilon_mm", 1e-4)),
        policy_id="horizontal_orientation_geometry_payload_exact_support",
    )
    return solve_extreme_point_ffd(
        items,
        containers,
        settings,
        policy=policy,
        orientation_provider=horizontal_orientation_provider(),
    )
