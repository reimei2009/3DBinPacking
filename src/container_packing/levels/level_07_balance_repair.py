"""Bounded local COG repair over an already feasible compound-root packing."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Callable

from ..algorithms.feasibility import PlacementFeasibilityPolicy
from ..algorithms.heuristics.extreme_point_core import ContainerState, place_candidate
from ..geometry.support import evaluate_support
from ..schemas import Container, Item, Placement
from .level_07_balance_points import BalanceAnchorPointProvider
from .load_balance import resolve_container_balance_attributes


CandidateValidator = Callable[[list[Placement]], bool]
Clock = Callable[[], float]


@dataclass
class BalanceRepairStats:
    candidates_evaluated: int = 0
    improving_candidates_validated: int = 0
    relocation_candidates: int = 0
    swap_candidates: int = 0
    partial_repack_candidates: int = 0
    accepted_moves: list[str] = field(default_factory=list)
    fixed_phase_seconds: float = 0.0
    extra_phase_seconds: float = 0.0
    termination_reason: str = "not_started"
    initial_max_violation: float = 0.0
    final_max_violation: float = 0.0

    def metadata(self) -> dict[str, object]:
        return {
            # Backward-compatible aggregate name used by CLI/reporting.
            "balance_repair_attempts": self.candidates_evaluated,
            "balance_repair_candidates_evaluated": self.candidates_evaluated,
            "balance_repair_improving_candidates_validated": self.improving_candidates_validated,
            "balance_repair_relocation_candidates": self.relocation_candidates,
            "balance_repair_swap_candidates": self.swap_candidates,
            "balance_repair_partial_repack_candidates": self.partial_repack_candidates,
            "balance_repair_accepted_moves": list(self.accepted_moves),
            "balance_repair_fixed_phase_seconds": self.fixed_phase_seconds,
            "balance_repair_extra_phase_seconds": self.extra_phase_seconds,
            "balance_repair_termination_reason": self.termination_reason,
            "balance_repair_initial_max_violation": self.initial_max_violation,
            "balance_repair_final_max_violation": self.final_max_violation,
        }


@dataclass(frozen=True)
class BalanceRepairResult:
    """Final balanced solution plus the best inherited-feasible search state.

    ``placements`` is populated only after the Level 7 final validator passes.
    ``best_feasible_placements`` may still violate Level 7 balance, but has
    passed the inherited Level 1-6 validator and is safe to hand to the next
    search phase.  It must never be reported as a solved packing.
    """

    placements: tuple[Placement, ...] | None
    best_feasible_placements: tuple[Placement, ...]
    stats: BalanceRepairStats
    opened_extra_containers: int


@dataclass(frozen=True)
class RootMassProperties:
    mass_kg: float
    center_offset_x_mm: float
    center_offset_y_mm: float


@dataclass
class BalanceMomentCache:
    values: dict[str, list[float]]
    mass_properties: dict[str, RootMassProperties] = field(default_factory=dict)

    @classmethod
    def from_placements(
        cls, placements: list[Placement],
        mass_properties: dict[str, RootMassProperties] | None = None,
    ) -> "BalanceMomentCache":
        values: dict[str, list[float]] = {}
        properties = dict(mass_properties or {})
        for value in placements:
            cls._apply(values, value, 1.0, properties)
        return cls(values, properties)

    @staticmethod
    def _apply(
        values: dict[str, list[float]], placement: Placement, sign: float,
        mass_properties: dict[str, RootMassProperties],
    ) -> None:
        row = values.setdefault(placement.container_id, [0.0, 0.0, 0.0])
        properties = mass_properties.get(placement.item_id)
        mass = placement.weight_kg if properties is None else properties.mass_kg
        offset_x = (
            placement.length_mm / 2.0
            if properties is None else properties.center_offset_x_mm
        )
        offset_y = (
            placement.width_mm / 2.0
            if properties is None else properties.center_offset_y_mm
        )
        weight = sign * mass
        row[0] += weight
        row[1] += weight * (placement.x_mm + offset_x)
        row[2] += weight * (placement.y_mm + offset_y)

    def changed(
        self, removed: list[Placement], added: list[Placement]
    ) -> "BalanceMomentCache":
        copy = {key: list(value) for key, value in self.values.items()}
        for value in removed:
            self._apply(copy, value, -1.0, self.mass_properties)
        for value in added:
            self._apply(copy, value, 1.0, self.mass_properties)
        return BalanceMomentCache(copy, self.mass_properties)

    def score(self, containers: dict[str, Container], balance_config: dict) -> tuple[float, ...]:
        attributes = resolve_container_balance_attributes(list(containers.values()), balance_config)
        violations: list[float] = []
        offsets: list[float] = []
        for container_id, (mass, moment_x, moment_y) in self.values.items():
            if mass <= 1e-9:
                continue
            container = containers[container_id]
            attr = attributes[container_id]
            dx = abs(moment_x / mass / container.length_mm - attr.target_longitudinal_ratio)
            dy = abs(moment_y / mass / container.width_mm - attr.target_lateral_ratio)
            violations.append(max(0.0, dx - attr.max_longitudinal_offset_ratio) + max(0.0, dy - attr.max_lateral_offset_ratio))
            offsets.append(dx + dy)
        return (
            max(violations, default=0.0),
            sum(violations),
            sum(offsets),
        )


class BalanceRepairEngine:
    """Deterministic first-improvement local repair with cooperative deadlines."""

    def __init__(
        self, *, policy: PlacementFeasibilityPolicy, balance_config: dict,
        coordinate_tolerance_mm: float, support_epsilon_mm: float,
        max_candidates: int, contributor_limit: int,
        mass_properties: dict[str, RootMassProperties] | None = None,
        clock: Clock = perf_counter,
    ) -> None:
        self.policy = policy
        self.balance_config = balance_config
        self.tolerance = coordinate_tolerance_mm
        self.support_epsilon = support_epsilon_mm
        self.max_candidates = max_candidates
        self.contributor_limit = contributor_limit
        self.mass_properties = dict(mass_properties or {})
        self.clock = clock
        self.anchor_provider = BalanceAnchorPointProvider(balance_config)
        if max_candidates <= 0:
            raise ValueError("balance_repair_max_candidates must be positive")
        if contributor_limit <= 0:
            raise ValueError("balance_repair_contributor_limit must be positive")

    def repair(
        self, items: list[Item], containers: list[Container], placements: list[Placement],
        *, validate_candidate: CandidateValidator, fixed_seconds: float,
        extra_seconds: float, extra_containers: list[Container],
        validate_final_candidate: CandidateValidator | None = None,
    ) -> BalanceRepairResult:
        """Repair through physically feasible intermediates, then validate balance.

        ``validate_candidate`` is the inherited Level 6 feasibility gate.  The
        optional final gate is Level 7's independent balance bundle.  Keeping
        these separate permits a sequence of improving COG moves without ever
        accepting a geometry/support/load violation.
        """
        validate_final = validate_final_candidate or validate_candidate
        stats = BalanceRepairStats()
        current = list(placements)
        container_map = {value.container_id: value for value in containers}
        moments = BalanceMomentCache.from_placements(
            current, self.mass_properties
        )
        initial_container_count = _used_container_count(current)
        current_score = _ranking(
            moments, current, container_map, self.balance_config
        )
        stats.initial_max_violation = current_score[0]
        fixed_started = self.clock()
        current, moments, current_score = self._phase(
            items, containers, current, moments, current_score, validate_candidate,
            deadline=fixed_started + max(0.0, fixed_seconds), stats=stats,
            allowed_container_counts={initial_container_count},
        )
        stats.fixed_phase_seconds = self.clock() - fixed_started
        if current_score[0] <= 1e-12 and validate_final(current):
            stats.termination_reason = "fixed_subset_valid"
            stats.final_max_violation = current_score[0]
            resolved = tuple(current)
            return BalanceRepairResult(resolved, resolved, stats, 0)

        if extra_seconds > 0 and extra_containers:
            extra_started = self.clock()
            # Rescue must inspect the newly opened container before the
            # already-exhausted fixed set. With a bounded candidate budget,
            # appending it last could consume the whole budget without ever
            # evaluating an actual rescue placement.
            pool = [extra_containers[0], *containers]
            container_map[extra_containers[0].container_id] = extra_containers[0]
            current, moments, current_score = self._phase(
                items, pool, current, moments, current_score, validate_candidate,
                deadline=extra_started + extra_seconds, stats=stats,
                allowed_container_counts={
                    initial_container_count, initial_container_count + 1
                },
            )
            stats.extra_phase_seconds = self.clock() - extra_started
            if current_score[0] <= 1e-12 and validate_final(current):
                stats.termination_reason = "extra_container_valid"
                stats.final_max_violation = current_score[0]
                opened = int(any(
                    value.container_id == extra_containers[0].container_id
                    for value in current
                ))
                resolved = tuple(current)
                return BalanceRepairResult(resolved, resolved, stats, opened)

        stats.final_max_violation = current_score[0]
        if stats.candidates_evaluated >= self.max_candidates:
            stats.termination_reason = "candidate_limit"
        elif stats.termination_reason in {"not_started", "phase_running"}:
            stats.termination_reason = "local_optimum"
        return BalanceRepairResult(None, tuple(current), stats, 0)

    def _phase(
        self, items: list[Item], containers: list[Container], current: list[Placement],
        moments: BalanceMomentCache, current_score: tuple[float, ...],
        validate_candidate: CandidateValidator, *, deadline: float,
        stats: BalanceRepairStats, allowed_container_counts: set[int],
    ) -> tuple[list[Placement], BalanceMomentCache, tuple[float, ...]]:
        item_by_id = {value.item_id: value for value in items}
        stats.termination_reason = "phase_running"
        while self.clock() < deadline and stats.candidates_evaluated < self.max_candidates:
            closures = support_closures(current, self.support_epsilon)
            contributors = _contributors(
                current, containers, self.balance_config, self.contributor_limit,
                self.mass_properties,
            )
            improved = False
            for item_id in contributors:
                if self.clock() >= deadline or stats.candidates_evaluated >= self.max_candidates:
                    break
                moving_ids = closures[item_id]
                moving = [value for value in current if value.item_id in moving_ids]
                remaining = [value for value in current if value.item_id not in moving_ids]
                root = next(value for value in moving if value.item_id == item_id)
                for target in containers:
                    state = _state(target, remaining, self.tolerance)
                    points = set(self.anchor_provider.points(state, item_by_id[item_id], _dimensions(root)))
                    points.add((root.x_mm, root.y_mm, root.z_mm))
                    for point in sorted(points, key=lambda value: (value[2], value[1], value[0])):
                        if self.clock() >= deadline or stats.candidates_evaluated >= self.max_candidates:
                            break
                        delta = (point[0] - root.x_mm, point[1] - root.y_mm, point[2] - root.z_mm)
                        added = [_shift(value, target.container_id, delta) for value in sorted(moving, key=lambda value: (value.z_mm, value.item_id))]
                        stats.candidates_evaluated += 1
                        stats.partial_repack_candidates += int(len(added) > 1)
                        stats.relocation_candidates += int(len(added) == 1)
                        if not _allows_group(state, added, self.policy, self.tolerance):
                            continue
                        candidate = [*remaining, *added]
                        if _used_container_count(candidate) not in allowed_container_counts:
                            continue
                        candidate_moments = moments.changed(moving, added)
                        candidate_score = _ranking(
                            candidate_moments, candidate,
                            {value.container_id: value for value in containers},
                            self.balance_config,
                        )
                        if candidate_score >= current_score:
                            continue
                        stats.improving_candidates_validated += 1
                        if not validate_candidate(candidate):
                            continue
                        current, moments, current_score = candidate, candidate_moments, candidate_score
                        stats.accepted_moves.append("partial_repack" if len(added) > 1 else "relocate")
                        improved = True
                        break
                    if improved:
                        break
                if improved:
                    break
            if not improved:
                swapped = self._try_swaps(
                    containers, current, moments, current_score, closures,
                    contributors, validate_candidate, deadline, stats,
                    allowed_container_counts,
                )
                if swapped is None:
                    break
                current, moments, current_score = swapped
        if stats.candidates_evaluated >= self.max_candidates:
            stats.termination_reason = "candidate_limit"
        elif self.clock() >= deadline:
            stats.termination_reason = "deadline"
        else:
            stats.termination_reason = "local_optimum"
        return current, moments, current_score

    def _try_swaps(
        self, containers: list[Container], current: list[Placement],
        moments: BalanceMomentCache, current_score: tuple[float, ...],
        closures: dict[str, set[str]], contributors: list[str],
        validate_candidate: CandidateValidator, deadline: float,
        stats: BalanceRepairStats,
        allowed_container_counts: set[int],
    ) -> tuple[list[Placement], BalanceMomentCache, tuple[float, ...]] | None:
        """Swap leaf roots only; support closures are never split."""
        leaves = [
            value for value in current
            if len(closures[value.item_id]) == 1
        ]
        sources = [
            value for item_id in contributors for value in leaves
            if value.item_id == item_id
        ]
        container_map = {value.container_id: value for value in containers}
        for left in sources:
            for right in sorted(
                leaves,
                key=lambda value: (value.container_id, value.z_mm, value.y_mm,
                                   value.x_mm, value.item_id),
            ):
                if left.item_id == right.item_id:
                    continue
                if self.clock() >= deadline or stats.candidates_evaluated >= self.max_candidates:
                    return None
                left_new = _at_origin(left, right)
                right_new = _at_origin(right, left)
                remaining = [
                    value for value in current
                    if value.item_id not in {left.item_id, right.item_id}
                ]
                states = {
                    container_id: _state(container_map[container_id], remaining, self.tolerance)
                    for container_id in {left_new.container_id, right_new.container_id}
                }
                stats.candidates_evaluated += 1
                stats.swap_candidates += 1
                trial_by_container: dict[str, list[Placement]] = {}
                for value in (left_new, right_new):
                    trial_by_container.setdefault(value.container_id, []).append(value)
                if any(
                    not _allows_group(states[container_id], values, self.policy, self.tolerance)
                    for container_id, values in trial_by_container.items()
                ):
                    continue
                candidate_moments = moments.changed(
                    [left, right], [left_new, right_new]
                )
                candidate = [*remaining, left_new, right_new]
                if _used_container_count(candidate) not in allowed_container_counts:
                    continue
                candidate_score = _ranking(
                    candidate_moments, candidate, container_map, self.balance_config
                )
                if candidate_score >= current_score:
                    continue
                stats.improving_candidates_validated += 1
                if not validate_candidate(candidate):
                    continue
                stats.accepted_moves.append("swap")
                return candidate, candidate_moments, candidate_score
        return None


def _state(container: Container, placements: list[Placement], tolerance: float) -> ContainerState:
    state = ContainerState(container)
    for value in sorted(
        (value for value in placements if value.container_id == container.container_id),
        key=lambda value: (value.z_mm, value.y_mm, value.x_mm, value.item_id),
    ):
        place_candidate(state, value, tolerance)
    return state


def support_closures(
    placements: list[Placement], epsilon_mm: float
) -> dict[str, set[str]]:
    children: dict[str, set[str]] = {value.item_id: set() for value in placements}
    for child in placements:
        support = evaluate_support(child, placements, epsilon_mm=epsilon_mm)
        for parent_id in support.supporting_item_ids:
            children[parent_id].add(child.item_id)
    closures: dict[str, set[str]] = {}
    for item_id in children:
        closure = {item_id}
        pending = [item_id]
        while pending:
            parent = pending.pop()
            for child_id in children[parent]:
                if child_id not in closure:
                    closure.add(child_id)
                    pending.append(child_id)
        closures[item_id] = closure
    return closures


def _contributors(
    placements: list[Placement], containers: list[Container],
    balance_config: dict, limit: int,
    mass_properties: dict[str, RootMassProperties] | None = None,
) -> list[str]:
    container_map = {value.container_id: value for value in containers}
    attributes = resolve_container_balance_attributes(containers, balance_config)
    moments = BalanceMomentCache.from_placements(placements, mass_properties)
    container_violations: list[tuple[float, str, float, float]] = []
    for container_id, (mass, mx, my) in moments.values.items():
        if mass <= 1e-9:
            continue
        container = container_map[container_id]
        attr = attributes[container_id]
        signed_x = mx / mass / container.length_mm - attr.target_longitudinal_ratio
        signed_y = my / mass / container.width_mm - attr.target_lateral_ratio
        excess_x = max(0.0, abs(signed_x) - attr.max_longitudinal_offset_ratio)
        excess_y = max(0.0, abs(signed_y) - attr.max_lateral_offset_ratio)
        container_violations.append((
            max(excess_x, excess_y), container_id, signed_x, signed_y
        ))
    violating = [value for value in container_violations if value[0] > 0.0]
    if not violating:
        return []
    _, worst_container_id, signed_x, signed_y = min(
        violating, key=lambda value: (-value[0], value[1])
    )
    container = container_map[worst_container_id]
    attr = attributes[worst_container_id]
    excess_x = max(0.0, abs(signed_x) - attr.max_longitudinal_offset_ratio)
    excess_y = max(0.0, abs(signed_y) - attr.max_lateral_offset_ratio)
    use_x = excess_x >= excess_y
    ranked: list[tuple[float, float, str]] = []
    for value in placements:
        if value.container_id != worst_container_id:
            continue
        properties = (mass_properties or {}).get(value.item_id)
        item_mass = value.weight_kg if properties is None else properties.mass_kg
        offset_x = value.length_mm / 2.0 if properties is None else properties.center_offset_x_mm
        offset_y = value.width_mm / 2.0 if properties is None else properties.center_offset_y_mm
        axis_contribution = item_mass * (
            signed_x * (
                (value.x_mm + offset_x) / container.length_mm
                - attr.target_longitudinal_ratio
            )
            if use_x
            else signed_y * (
                (value.y_mm + offset_y) / container.width_mm
                - attr.target_lateral_ratio
            )
        )
        ranked.append((-axis_contribution, -item_mass, value.item_id))
    return [item_id for _, _, item_id in sorted(ranked)[:limit]]


def _shift(value: Placement, container_id: str, delta: tuple[float, float, float]) -> Placement:
    return Placement(
        value.item_id, container_id,
        value.x_mm + delta[0], value.y_mm + delta[1], value.z_mm + delta[2],
        value.length_mm, value.width_mm, value.height_mm, value.weight_kg,
        value.orientation_code,
    )


def _at_origin(value: Placement, origin: Placement) -> Placement:
    return Placement(
        value.item_id, origin.container_id,
        origin.x_mm, origin.y_mm, origin.z_mm,
        value.length_mm, value.width_mm, value.height_mm, value.weight_kg,
        value.orientation_code,
    )


def _allows_group(
    state: ContainerState, placements: list[Placement],
    policy: PlacementFeasibilityPolicy, tolerance: float,
) -> bool:
    trial = ContainerState(
        state.container, list(state.placements), set(state.extreme_points), state.loaded_weight_kg
    )
    for value in placements:
        if not policy.allows(
            trial.container, trial.placements, value,
            loaded_weight_kg=trial.loaded_weight_kg, tolerance=tolerance,
        ):
            return False
        place_candidate(trial, value, tolerance)
    return True


def _dimensions(placement: Placement):
    from ..geometry.orientation import OrientedDimensions
    return OrientedDimensions(
        placement.orientation_code, placement.length_mm,
        placement.width_mm, placement.height_mm,
    )


def _ranking(
    moments: BalanceMomentCache, placements: list[Placement],
    containers: dict[str, Container], balance_config: dict,
) -> tuple[float, ...]:
    cog = moments.score(containers, balance_config)
    used_ids = {value.container_id for value in placements}
    cost = sum(containers[value].cost for value in used_ids)
    compactness = 0.0
    for container_id in used_ids:
        values = [
            value for value in placements if value.container_id == container_id
        ]
        compactness += (
            max(value.x_mm + value.length_mm for value in values)
            * max(value.y_mm + value.width_mm for value in values)
            * max(value.z_mm + value.height_mm for value in values)
        )
    return (*cog, float(cost), compactness)


def _used_container_count(placements: list[Placement]) -> int:
    return len({value.container_id for value in placements})
