"""Deterministic fixed-orientation Extreme-Point First-Fit Decreasing heuristic."""

from __future__ import annotations

from typing import Any
from math import isfinite

from scipy.optimize import OptimizeResult

from ..contracts import AlgorithmOutcome
from ..feasibility import FixedOrientationFeasibilityPolicy, PlacementFeasibilityPolicy
from ..orientation import OrientationProvider, fixed_orientation_provider
from .extreme_point_core import constructive_search, pack_order_first_fit, resolved_item_order
from .first_fit_selection import FirstFitCandidateSelectionPolicy
from .candidate_points import CandidatePointProvider
from .container_subset_selection import ContainerSubsetSelectionPolicy
from .container_assignment import ContainerAssignmentPlanner
from ...schemas import Container, Item, SolveResult


def solve(
    items: list[Item], containers: list[Container], settings: dict[str, Any] | None = None,
    *, policy: PlacementFeasibilityPolicy | None = None,
    orientation_provider: OrientationProvider | None = None,
    candidate_selection_policy: FirstFitCandidateSelectionPolicy | None = None,
    candidate_point_provider: CandidatePointProvider | None = None,
    container_subset_policy: ContainerSubsetSelectionPolicy | None = None,
    container_assignment_planner: ContainerAssignmentPlanner | None = None,
) -> AlgorithmOutcome:
    """Pack all items with an explicit orientation provider; not globally optimal."""
    settings = settings or {}
    tolerance = float(settings.get("coordinate_tolerance_mm", 1e-6))
    subset_limit = int(settings.get("subset_enumeration_limit", 12))
    if subset_limit <= 0:
        raise ValueError("subset_enumeration_limit must be positive")
    selected_policy = policy or FixedOrientationFeasibilityPolicy()
    selected_orientation_provider = orientation_provider or fixed_orientation_provider()
    deadline = settings.get("constructive_deadline_monotonic")
    if deadline is not None and (not isinstance(deadline, (int, float)) or not isfinite(float(deadline))):
        raise ValueError("constructive_deadline_monotonic must be a finite monotonic timestamp")
    ordered_items = resolved_item_order(items, settings)
    def pack_order(items, containers, tolerance, stats, policy, preference_policy):
        del preference_policy  # FFD remains the fast comparator in this checkpoint.
        return pack_order_first_fit(
            items, containers, tolerance, stats, policy,
            orientation_provider=selected_orientation_provider,
            candidate_selection_policy=candidate_selection_policy,
            candidate_point_provider=candidate_point_provider,
        )
    search = constructive_search(
        ordered_items, containers, tolerance, subset_limit, pack_order, selected_policy,
        deadline_monotonic=None if deadline is None else float(deadline),
        container_subset_policy=container_subset_policy,
        container_assignment_planner=container_assignment_planner,
    )

    priority = 1.0 + sum(value.cost for value in containers)
    if search.time_limit_reached:
        solve = SolveResult(
            status="TIME_LIMIT",
            message="Extreme-Point FFD stopped because its construction deadline was reached.",
            objective_value=None, vector=None, raw_result=OptimizeResult(),
        )
    elif search.placements is None:
        solve = SolveResult(
            status="INFEASIBLE_HEURISTIC",
            message="Heuristic found no complete packing; this is not a proof of infeasibility.",
            objective_value=None, vector=None, raw_result=OptimizeResult(),
        )
    else:
        used_ids = {value.container_id for value in search.placements}
        used_cost = sum(value.cost for value in containers if value.container_id in used_ids)
        objective = len(used_ids) * priority + used_cost
        solve = SolveResult(
            status="FEASIBLE",
            message="Deterministic Extreme-Point FFD found a complete packing.",
            objective_value=float(objective), vector=None, raw_result=OptimizeResult(),
        )
    return AlgorithmOutcome(
        solve=solve,
        placements=[] if search.placements is None else search.placements,
        backend="deterministic/extreme-point-ffd",
        metadata={
            "algorithm_kind": "constructive_heuristic",
            "optimality_proven": False,
            "item_ordering": "decreasing_volume_max_dimension_weight",
            "point_ordering": "bottom_left_back_z_y_x",
            "container_selection_strategy": "minimum_count_then_cost_subset_search",
            "subset_enumeration_limit": subset_limit,
            "candidate_subsets_evaluated": search.stats.candidate_subsets_evaluated,
            "packing_attempts": search.stats.packing_attempts,
            "extreme_points_evaluated": search.stats.extreme_points_evaluated,
            "orientation_candidates_evaluated": search.stats.orientation_candidates_evaluated,
            "candidate_container_ids": [value.container_id for value in search.chosen_containers],
            "n_items": len(items),
            "n_containers": len(containers),
            "construction_time_limit_reached": search.time_limit_reached,
            **({} if search.attempt is None else search.attempt.metadata()),
            **selected_orientation_provider.metadata(),
            **selected_policy.metadata(),
            **({} if candidate_selection_policy is None else candidate_selection_policy.metadata()),
            **({} if candidate_point_provider is None else candidate_point_provider.metadata()),
            **({} if container_subset_policy is None else container_subset_policy.metadata()),
            **(
                {}
                if container_subset_policy is None
                else {"container_subset_attempts": search.stats.subset_attempts}
            ),
            "container_assignment_plans_evaluated": search.stats.assignment_plans_evaluated,
            **search.stats.selected_assignment_metadata,
            **(
                {} if container_assignment_planner is None
                else container_assignment_planner.metadata()
            ),
        },
    )


solve_level1 = solve
