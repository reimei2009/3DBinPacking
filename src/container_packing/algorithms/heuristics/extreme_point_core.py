"""Shared fixed-orientation Extreme-Point construction primitives."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Callable

from ..contracts import (
    AttemptStatistics,
    ConstructionAttemptResult,
    ConstructionTerminationReason,
    UnpackedItemDiagnostic,
)
from ..feasibility import FixedOrientationFeasibilityPolicy, PlacementFeasibilityPolicy
from ..orientation import OrientationProvider, fixed_orientation_provider
from ...geometry.orientation import OrientedDimensions
from ...schemas import Container, Item, Placement
from .constructive_common import candidate_subsets, container_orders, item_sort_key
from .container_subset_selection import ContainerSubsetSelectionPolicy
from .container_assignment import (
    ContainerAssignmentPlanner,
    ContainerPreferencePolicy,
)
from .first_fit_selection import FirstFitCandidate, FirstFitCandidateSelectionPolicy
from .candidate_points import CandidatePointProvider

Point = tuple[float, float, float]
PackOrder = Callable[
    [
        list[Item], tuple[Container, ...], float, "SearchStats",
        PlacementFeasibilityPolicy, ContainerPreferencePolicy | None,
    ],
    ConstructionAttemptResult,
]


@dataclass
class ContainerState:
    container: Container
    placements: list[Placement] = field(default_factory=list)
    extreme_points: set[Point] = field(default_factory=lambda: {(0.0, 0.0, 0.0)})
    loaded_weight_kg: float = 0.0

    @property
    def loaded_volume_mm3(self) -> float:
        return sum(
            value.length_mm * value.width_mm * value.height_mm
            for value in self.placements
        )


@dataclass
class SearchStats:
    candidate_subsets_evaluated: int = 0
    packing_attempts: int = 0
    extreme_points_evaluated: int = 0
    orientation_candidates_evaluated: int = 0
    deadline_monotonic: float | None = None
    time_limit_reached: bool = False
    subset_attempts: list[dict[str, object]] = field(default_factory=list)
    assignment_plans_evaluated: int = 0
    selected_assignment_metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ConstructiveSearchResult:
    attempt: ConstructionAttemptResult | None
    chosen_containers: tuple[Container, ...]
    stats: SearchStats
    time_limit_reached: bool = False

    @property
    def placements(self) -> list[Placement] | None:
        """Chỉ expose placements như nghiệm khi attempt đã complete."""
        if self.attempt is None or not self.attempt.complete:
            return None
        return list(self.attempt.placements)

    @property
    def best_partial_attempt(self) -> ConstructionAttemptResult | None:
        if self.attempt is None or self.attempt.complete:
            return None
        return self.attempt


def _deadline_reached(stats: SearchStats) -> bool:
    """Stop constructive search at a caller-owned monotonic deadline."""
    if stats.deadline_monotonic is None or perf_counter() < stats.deadline_monotonic:
        return False
    stats.time_limit_reached = True
    return True


def candidate_placement(
    state: ContainerState,
    item: Item,
    point: Point,
    dimensions: OrientedDimensions | None = None,
) -> Placement:
    x, y, z = point
    selected_dimensions = dimensions or fixed_orientation_provider().candidates(item)[0]
    return Placement(
        item_id=item.item_id, container_id=state.container.container_id,
        x_mm=x, y_mm=y, z_mm=z,
        length_mm=selected_dimensions.length_mm,
        width_mm=selected_dimensions.width_mm,
        height_mm=selected_dimensions.height_mm,
        weight_kg=item.weight_kg,
        orientation_code=selected_dimensions.code,
    )


def fits(
    state: ContainerState,
    item: Item,
    point: Point,
    tolerance: float,
    policy: PlacementFeasibilityPolicy | None = None,
    dimensions: OrientedDimensions | None = None,
) -> bool:
    selected_policy = policy or FixedOrientationFeasibilityPolicy()
    return selected_policy.allows(
        state.container,
        state.placements,
        candidate_placement(state, item, point, dimensions),
        loaded_weight_kg=state.loaded_weight_kg,
        tolerance=tolerance,
    )


def _point_inside_box(point: Point, box: Placement, tolerance: float) -> bool:
    x, y, z = point
    return (
        box.x_mm - tolerance <= x < box.x_mm + box.length_mm - tolerance
        and box.y_mm - tolerance <= y < box.y_mm + box.width_mm - tolerance
        and box.z_mm - tolerance <= z < box.z_mm + box.height_mm - tolerance
    )


def update_extreme_points(state: ContainerState, placement: Placement, tolerance: float) -> None:
    state.extreme_points.update({
        (placement.x_mm + placement.length_mm, placement.y_mm, placement.z_mm),
        (placement.x_mm, placement.y_mm + placement.width_mm, placement.z_mm),
        (placement.x_mm, placement.y_mm, placement.z_mm + placement.height_mm),
    })
    container = state.container
    state.extreme_points = {
        point for point in state.extreme_points
        if point[0] <= container.length_mm + tolerance
        and point[1] <= container.width_mm + tolerance
        and point[2] <= container.height_mm + tolerance
        and not any(_point_inside_box(point, box, tolerance) for box in state.placements)
    }


def place_item(state: ContainerState, item: Item, point: Point, tolerance: float) -> Placement:
    placement = candidate_placement(state, item, point)
    return place_candidate(state, placement, tolerance)


def place_candidate(state: ContainerState, placement: Placement, tolerance: float) -> Placement:
    """Commit an already feasibility-checked candidate to its container state."""
    state.placements.append(placement)
    state.loaded_weight_kg += placement.weight_kg
    update_extreme_points(state, placement, tolerance)
    return placement


def initialized_container_states(
    containers: tuple[Container, ...],
    initial_placements: tuple[Placement, ...] = (),
    *,
    tolerance: float,
) -> list[ContainerState]:
    """Khởi tạo EP state từ phần nghiệm được giữ cố định khi partial repack.

    Seed chỉ đến từ incumbent đã hợp lệ. Hàm vẫn kiểm tra container và item ID
    để lỗi orchestration không âm thầm tạo một state không nhất quán.
    """
    states = [ContainerState(container) for container in containers]
    by_container = {state.container.container_id: state for state in states}
    seen_items: set[str] = set()
    for placement in sorted(
        initial_placements,
        key=lambda value: (
            value.container_id, value.z_mm, value.y_mm, value.x_mm, value.item_id,
        ),
    ):
        if placement.item_id in seen_items:
            raise ValueError(
                f"construction_initial_placements duplicates item {placement.item_id}"
            )
        try:
            state = by_container[placement.container_id]
        except KeyError as exc:
            raise ValueError(
                "construction_initial_placements references container outside "
                f"the fixed subset: {placement.container_id}"
            ) from exc
        seen_items.add(placement.item_id)
        place_candidate(state, placement, tolerance)
    return states


def _flatten_placements(states: list[ContainerState]) -> tuple[Placement, ...]:
    return tuple(placement for state in states for placement in state.placements)


def _attempt_signature(
    items: list[Item], containers: tuple[Container, ...], algorithm_id: str,
) -> str:
    return "|".join((
        algorithm_id,
        ",".join(value.container_id for value in containers),
        ",".join(value.item_id for value in items),
    ))


def _complete_attempt(
    items: list[Item], containers: tuple[Container, ...], states: list[ContainerState],
    algorithm_id: str, statistics: AttemptStatistics,
) -> ConstructionAttemptResult:
    return ConstructionAttemptResult(
        complete=True,
        placements=_flatten_placements(states),
        unpacked_items=(),
        failed_item_id=None,
        termination_reason=ConstructionTerminationReason.COMPLETE,
        attempt_signature=_attempt_signature(items, containers, algorithm_id),
        statistics=statistics,
        subset_ids=tuple(value.container_id for value in containers),
        container_order=tuple(value.container_id for value in containers),
        algorithm_id=algorithm_id,
    )


def _incomplete_attempt(
    items: list[Item], failed_index: int, containers: tuple[Container, ...],
    states: list[ContainerState], algorithm_id: str,
    reason: ConstructionTerminationReason, failed_item_statistics: AttemptStatistics,
    attempt_statistics: AttemptStatistics | None = None,
) -> ConstructionAttemptResult:
    diagnostics: list[UnpackedItemDiagnostic] = []
    for index, item in enumerate(items[failed_index:], start=failed_index):
        is_failed_item = index == failed_index
        diagnostics.append(UnpackedItemDiagnostic(
            item_id=item.item_id,
            reason_code=(
                str(reason) if is_failed_item else
                str(ConstructionTerminationReason.NOT_ATTEMPTED_AFTER_FAILURE)
            ),
            containers_tested=failed_item_statistics.containers_tested if is_failed_item else 0,
            orientations_tested=failed_item_statistics.orientations_tested if is_failed_item else 0,
            candidate_positions_tested=(
                failed_item_statistics.candidate_positions_tested if is_failed_item else 0
            ),
        ))
    return ConstructionAttemptResult(
        complete=False,
        placements=_flatten_placements(states),
        unpacked_items=tuple(diagnostics),
        failed_item_id=items[failed_index].item_id,
        termination_reason=str(reason),
        attempt_signature=_attempt_signature(items, containers, algorithm_id),
        statistics=attempt_statistics or failed_item_statistics,
        subset_ids=tuple(value.container_id for value in containers),
        container_order=tuple(value.container_id for value in containers),
        algorithm_id=algorithm_id,
        search_score=(float(len(diagnostics)), -float(len(_flatten_placements(states)))),
    )


def pack_order_first_fit(
    items: list[Item], containers: tuple[Container, ...], tolerance: float, stats: SearchStats,
    policy: PlacementFeasibilityPolicy, *, orientation_provider: OrientationProvider | None = None,
    candidate_selection_policy: FirstFitCandidateSelectionPolicy | None = None,
    candidate_point_provider: CandidatePointProvider | None = None,
    initial_placements: tuple[Placement, ...] = (),
) -> ConstructionAttemptResult:
    """Place the first feasible extreme-point/orientation candidate in order."""
    selected_provider = orientation_provider or fixed_orientation_provider()
    states = initialized_container_states(
        containers, initial_placements, tolerance=tolerance,
    )
    start_candidates = stats.extreme_points_evaluated
    start_orientations = stats.orientation_candidates_evaluated
    attempt_containers_tested = 0
    for item_index, item in enumerate(items):
        containers_tested = 0
        candidates_tested = 0
        orientations_tested = 0
        if _deadline_reached(stats):
            return _incomplete_attempt(
                items, item_index, containers, states, "extreme_point_ffd",
                ConstructionTerminationReason.TIME_LIMIT_REACHED,
                AttemptStatistics(),
            )
        if candidate_selection_policy is not None:
            selected: tuple[ContainerState, Placement] | None = None
            for state in states:
                containers_tested += 1
                attempt_containers_tested += 1
                candidates: list[FirstFitCandidate] = []
                if candidate_point_provider is None:
                    candidates_iter = (
                        (point, orientation_rank, dimensions)
                        for point in _candidate_points(state, item, selected_provider.candidates(item)[0], None)
                        for orientation_rank, dimensions in enumerate(selected_provider.candidates(item))
                    )
                else:
                    candidates_iter = (
                        (point, orientation_rank, dimensions)
                        for orientation_rank, dimensions in enumerate(selected_provider.candidates(item))
                        for point in _candidate_points(state, item, dimensions, candidate_point_provider)
                    )
                for point, orientation_rank, dimensions in candidates_iter:
                    if _deadline_reached(stats):
                        return _incomplete_attempt(
                            items, item_index, containers, states, "extreme_point_ffd",
                            ConstructionTerminationReason.TIME_LIMIT_REACHED,
                            AttemptStatistics(
                                containers_tested, candidates_tested, orientations_tested,
                            ),
                            AttemptStatistics(
                                attempt_containers_tested,
                                stats.extreme_points_evaluated - start_candidates,
                                stats.orientation_candidates_evaluated - start_orientations,
                            ),
                        )
                    stats.extreme_points_evaluated += 1
                    stats.orientation_candidates_evaluated += 1
                    candidates_tested += 1
                    orientations_tested += 1
                    candidate = candidate_placement(state, item, point, dimensions)
                    if selected_policy_allows(state, candidate, tolerance, policy):
                        candidates.append(FirstFitCandidate(
                            candidate, (float(point[2]), float(point[1]), float(point[0]), orientation_rank)
                        ))
                if candidates:
                    selected = state, candidate_selection_policy.select(state, tuple(candidates))
                    break
            if selected is None:
                return _incomplete_attempt(
                    items, item_index, containers, states, "extreme_point_ffd",
                    ConstructionTerminationReason.NO_FEASIBLE_CANDIDATE,
                    AttemptStatistics(
                        containers_tested, candidates_tested, orientations_tested,
                    ),
                    AttemptStatistics(
                        attempt_containers_tested,
                        stats.extreme_points_evaluated - start_candidates,
                        stats.orientation_candidates_evaluated - start_orientations,
                    ),
                )
            place_candidate(selected[0], selected[1], tolerance)
            continue
        selected: tuple[ContainerState, Placement] | None = None
        for state in states:
            containers_tested += 1
            attempt_containers_tested += 1
            if candidate_point_provider is None:
                candidates_iter = (
                    (point, dimensions)
                    for point in _candidate_points(state, item, selected_provider.candidates(item)[0], None)
                    for dimensions in selected_provider.candidates(item)
                )
            else:
                candidates_iter = (
                    (point, dimensions)
                    for dimensions in selected_provider.candidates(item)
                    for point in _candidate_points(state, item, dimensions, candidate_point_provider)
                )
            for point, dimensions in candidates_iter:
                if _deadline_reached(stats):
                    return _incomplete_attempt(
                        items, item_index, containers, states, "extreme_point_ffd",
                        ConstructionTerminationReason.TIME_LIMIT_REACHED,
                        AttemptStatistics(
                            containers_tested, candidates_tested, orientations_tested,
                        ),
                        AttemptStatistics(
                            attempt_containers_tested,
                            stats.extreme_points_evaluated - start_candidates,
                            stats.orientation_candidates_evaluated - start_orientations,
                        ),
                    )
                stats.extreme_points_evaluated += 1
                stats.orientation_candidates_evaluated += 1
                candidates_tested += 1
                orientations_tested += 1
                candidate = candidate_placement(state, item, point, dimensions)
                if selected_policy_allows(state, candidate, tolerance, policy):
                    selected = state, candidate
                    break
            if selected is not None:
                break
        if selected is None:
            return _incomplete_attempt(
                items, item_index, containers, states, "extreme_point_ffd",
                ConstructionTerminationReason.NO_FEASIBLE_CANDIDATE,
                AttemptStatistics(
                    containers_tested, candidates_tested, orientations_tested,
                ),
                AttemptStatistics(
                    attempt_containers_tested,
                    stats.extreme_points_evaluated - start_candidates,
                    stats.orientation_candidates_evaluated - start_orientations,
                ),
            )
        place_candidate(selected[0], selected[1], tolerance)
    return _complete_attempt(
        items, containers, states, "extreme_point_ffd",
        AttemptStatistics(
            attempt_containers_tested,
            stats.extreme_points_evaluated - start_candidates,
            stats.orientation_candidates_evaluated - start_orientations,
        ),
    )


def _candidate_points(
    state: ContainerState,
    item: Item,
    dimensions: OrientedDimensions,
    provider: CandidatePointProvider | None,
) -> tuple[Point, ...]:
    """Return canonical extreme points or a deterministic provider extension."""
    if provider is None:
        return tuple(sorted(state.extreme_points, key=lambda value: (value[2], value[1], value[0])))
    return provider.points(state, item, dimensions)


def resolved_item_order(items: list[Item], settings: dict) -> list[Item]:
    """Use an explicit deterministic repair order when supplied by local search."""
    requested = settings.get("item_order_override")
    if requested is None:
        return sorted(items, key=item_sort_key)
    if not isinstance(requested, list) or set(requested) != {item.item_id for item in items}:
        raise ValueError("item_order_override must contain every item ID exactly once")
    if len(requested) != len(items):
        raise ValueError("item_order_override contains duplicate item IDs")
    by_id = {item.item_id: item for item in items}
    return [by_id[str(item_id)] for item_id in requested]


def selected_policy_allows(
    state: ContainerState,
    candidate: Placement,
    tolerance: float,
    policy: PlacementFeasibilityPolicy,
) -> bool:
    """Evaluate a concrete candidate so its orientation reaches the policy."""
    return policy.allows(
        state.container,
        state.placements,
        candidate,
        loaded_weight_kg=state.loaded_weight_kg,
        tolerance=tolerance,
    )


def constructive_search(
    ordered_items: list[Item], containers: list[Container], tolerance: float,
    subset_limit: int, pack_order: PackOrder, policy: PlacementFeasibilityPolicy,
    *, deadline_monotonic: float | None = None,
    container_subset_policy: ContainerSubsetSelectionPolicy | None = None,
    container_assignment_planner: ContainerAssignmentPlanner | None = None,
) -> ConstructiveSearchResult:
    total_weight = sum(value.weight_kg for value in ordered_items)
    total_volume = sum(value.volume_m3 for value in ordered_items)
    stats = SearchStats(deadline_monotonic=deadline_monotonic)
    best_partial: ConstructionAttemptResult | None = None
    best_partial_containers: tuple[Container, ...] = ()
    subsets = (
        candidate_subsets(containers, subset_limit)
        if container_subset_policy is None
        else container_subset_policy.candidates(containers, ordered_items)
    )
    for subset in subsets:
        if _deadline_reached(stats):
            return ConstructiveSearchResult(None, (), stats, time_limit_reached=True)
        stats.candidate_subsets_evaluated += 1
        attempt = {
            "container_ids": [value.container_id for value in subset],
            "container_count": len(subset),
            "total_cost": sum(value.cost for value in subset),
            "status": "packing_failed",
        }
        if sum(value.max_weight_kg for value in subset) + tolerance < total_weight:
            attempt["status"] = "aggregate_payload_infeasible"
            if len(stats.subset_attempts) < 128:
                stats.subset_attempts.append(attempt)
            continue
        if sum(value.volume_m3 for value in subset) + tolerance < total_volume:
            attempt["status"] = "aggregate_volume_infeasible"
            if len(stats.subset_attempts) < 128:
                stats.subset_attempts.append(attempt)
            continue
        plans = (
            (None,)
            if container_assignment_planner is None
            else container_assignment_planner.plans(
                subset, ordered_items, deadline_monotonic=deadline_monotonic
            )
        )
        if not plans:
            attempt["status"] = (
                "time_limit" if _deadline_reached(stats)
                else "assignment_planner_found_no_plan"
            )
            if len(stats.subset_attempts) < 128:
                stats.subset_attempts.append(attempt)
            if stats.time_limit_reached:
                return ConstructiveSearchResult(
                    None, (), stats, time_limit_reached=True
                )
            continue
        for plan in plans:
            if plan is not None:
                stats.assignment_plans_evaluated += 1
            orders = (
                (tuple(sorted(subset, key=lambda value: value.container_id)),)
                if plan is not None
                else container_orders(subset)
            )
            for container_order in orders:
                preference_policy = (
                    None if plan is None else ContainerPreferencePolicy(plan)
                )
                stats.packing_attempts += 1
                pack_attempt = pack_order(
                    ordered_items, container_order, tolerance, stats,
                    policy, preference_policy,
                )
                if (
                    not pack_attempt.complete
                    and (
                        best_partial is None
                        or len(pack_attempt.placements) > len(best_partial.placements)
                    )
                ):
                    best_partial = pack_attempt
                    best_partial_containers = container_order
                if stats.time_limit_reached:
                    attempt["status"] = "time_limit"
                    if len(stats.subset_attempts) < 128:
                        stats.subset_attempts.append(attempt)
                    return ConstructiveSearchResult(
                        pack_attempt, container_order, stats, time_limit_reached=True,
                    )
                if pack_attempt.complete:
                    attempt["status"] = "feasible"
                    if plan is not None:
                        attempt["assignment"] = plan.metadata()
                        stats.selected_assignment_metadata = {
                            **plan.metadata(),
                            **preference_policy.metadata(list(pack_attempt.placements)),
                        }
                    if len(stats.subset_attempts) < 128:
                        stats.subset_attempts.append(attempt)
                    chosen = tuple({
                        value.container_id: value for value in container_order
                    }.values())
                    return ConstructiveSearchResult(pack_attempt, chosen, stats)
        if len(stats.subset_attempts) < 128:
            stats.subset_attempts.append(attempt)
    return ConstructiveSearchResult(best_partial, best_partial_containers, stats)
