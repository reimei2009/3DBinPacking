"""Bounded local strict-LIFO repair over a Level 1--7-valid packing.

The engine deliberately does not rebuild all items.  It moves a leaf root or
its complete support closure, keeps the current containers fixed first, and
uses the inherited independent validator before accepting an improvement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Callable

from ..algorithms.feasibility import PlacementFeasibilityPolicy
from ..algorithms.heuristics.extreme_point_core import candidate_placement
from ..schemas import Container, Item, Placement
from .level_07_balance_repair import _allows_group, _dimensions, _shift, _state, support_closures
from .level_08_delivery_scoring import DeliveryDoorPointProvider
from .unloading import UnloadingSettings, is_later_priority_direct_blocker


CandidateValidator = Callable[[list[Placement]], bool]


@dataclass
class DeliveryRepairStats:
    candidates_evaluated: int = 0
    improving_candidates_validated: int = 0
    relocation_candidates: int = 0
    transfer_candidates: int = 0
    swap_candidates: int = 0
    partial_repack_candidates: int = 0
    neighborhood_candidates: int = 0
    neighborhood_attempts: int = 0
    accepted_moves: list[str] = field(default_factory=list)
    fixed_phase_seconds: float = 0.0
    extra_phase_seconds: float = 0.0
    initial_rehandles: int = 0
    final_rehandles: int = 0
    initial_violations: int = 0
    final_violations: int = 0
    termination_reason: str = "not_started"

    def metadata(self) -> dict[str, object]:
        return {
            "delivery_repair_candidates_evaluated": self.candidates_evaluated,
            "delivery_repair_improving_candidates_validated": self.improving_candidates_validated,
            "delivery_repair_relocation_candidates": self.relocation_candidates,
            "delivery_repair_transfer_candidates": self.transfer_candidates,
            "delivery_repair_swap_candidates": self.swap_candidates,
            "delivery_repair_partial_repack_candidates": self.partial_repack_candidates,
            "delivery_repair_neighborhood_candidates": self.neighborhood_candidates,
            "delivery_repair_neighborhood_attempts": self.neighborhood_attempts,
            "delivery_repair_accepted_moves": list(self.accepted_moves),
            "delivery_repair_fixed_phase_seconds": self.fixed_phase_seconds,
            "delivery_repair_extra_phase_seconds": self.extra_phase_seconds,
            "delivery_repair_initial_direct_rehandles": self.initial_rehandles,
            "delivery_repair_final_direct_rehandles": self.final_rehandles,
            "delivery_repair_initial_lifo_violations": self.initial_violations,
            "delivery_repair_final_lifo_violations": self.final_violations,
            "delivery_repair_termination_reason": self.termination_reason,
        }


@dataclass(frozen=True)
class DeliveryRepairResult:
    placements: tuple[Placement, ...] | None
    best_inherited_valid_placements: tuple[Placement, ...]
    stats: DeliveryRepairStats
    opened_extra_container: bool


@dataclass(frozen=True)
class DeliveryBlockerCache:
    """Immutable strict-LIFO edge set with O(k*n) updates for local moves."""

    items_by_id: dict[str, Item]
    settings: UnloadingSettings
    edges: frozenset[tuple[str, str]]

    @classmethod
    def from_placements(
        cls, items_by_id: dict[str, Item], placements: list[Placement], settings: UnloadingSettings
    ) -> "DeliveryBlockerCache":
        return cls(items_by_id, settings, frozenset(_edges(items_by_id, placements, settings)))

    @property
    def score(self) -> tuple[int, int]:
        return (len(self.edges), len({target for target, _ in self.edges}))

    def changed(
        self, remaining: list[Placement], added: list[Placement]
    ) -> "DeliveryBlockerCache":
        moved_ids = {value.item_id for value in added}
        edges = {
            edge for edge in self.edges
            if edge[0] not in moved_ids and edge[1] not in moved_ids
        }
        population = [*remaining, *added]
        for target in added:
            for other in population:
                if is_later_priority_direct_blocker(self.items_by_id, target, other, self.settings):
                    edges.add((target.item_id, other.item_id))
        for target in remaining:
            for blocker in added:
                if is_later_priority_direct_blocker(self.items_by_id, target, blocker, self.settings):
                    edges.add((target.item_id, blocker.item_id))
        return DeliveryBlockerCache(self.items_by_id, self.settings, frozenset(edges))

    def contributors(self, limit: int) -> list[str]:
        counts: dict[str, int] = {}
        for target, blocker in self.edges:
            counts[target] = counts.get(target, 0) + 1
            counts[blocker] = counts.get(blocker, 0) + 1
        return [item_id for item_id, _ in sorted(counts.items(), key=lambda value: (-value[1], value[0]))[:limit]]


class DeliveryRepairEngine:
    """First-improvement local search driven by strict-LIFO blocker edges."""

    def __init__(
        self, *, policy: PlacementFeasibilityPolicy, settings: UnloadingSettings,
        coordinate_tolerance_mm: float, support_epsilon_mm: float,
        max_candidates: int, contributor_limit: int,
        relocation_transfer_max_candidates: int | None = None,
        swap_max_candidates: int | None = None,
        neighborhood_max_candidates: int | None = None,
        extra_max_candidates: int | None = None,
        neighborhood_sizes: tuple[int, ...] = (4, 8, 12),
        operator_time_fractions: tuple[float, float, float] = (0.5, 0.25, 0.25),
    ) -> None:
        if max_candidates <= 0 or contributor_limit <= 0:
            raise ValueError("Delivery repair candidate and contributor limits must be positive")
        self.policy = policy
        self.settings = settings
        self.tolerance = coordinate_tolerance_mm
        self.support_epsilon = support_epsilon_mm
        self.max_candidates = max_candidates
        self.contributor_limit = contributor_limit
        self.points = DeliveryDoorPointProvider(settings)
        self.relocation_transfer_max_candidates = (
            max(0, relocation_transfer_max_candidates)
            if relocation_transfer_max_candidates is not None else max(1, max_candidates // 2)
        )
        self.swap_max_candidates = (
            max(0, swap_max_candidates)
            if swap_max_candidates is not None else max(1, max_candidates // 4)
        )
        self.neighborhood_max_candidates = (
            max(0, neighborhood_max_candidates)
            if neighborhood_max_candidates is not None else max(1, max_candidates // 4)
        )
        self.extra_max_candidates = (
            max(0, extra_max_candidates)
            if extra_max_candidates is not None else max_candidates
        )
        self.neighborhood_sizes = tuple(sorted({value for value in neighborhood_sizes if value > 1}))
        if not self.neighborhood_sizes:
            raise ValueError("Delivery repair requires a neighborhood size greater than one")
        if len(operator_time_fractions) != 3 or any(value < 0 for value in operator_time_fractions):
            raise ValueError("Delivery repair requires three non-negative operator time fractions")
        total_fraction = sum(operator_time_fractions)
        if total_fraction <= 0:
            raise ValueError("Delivery repair operator time fractions must have a positive sum")
        self.operator_time_fractions = tuple(value / total_fraction for value in operator_time_fractions)

    def repair(
        self, items: list[Item], fixed_containers: list[Container], placements: list[Placement], *,
        validate_inherited: CandidateValidator, validate_final: CandidateValidator,
        fixed_seconds: float, extra_seconds: float, extra_container: Container | None,
    ) -> DeliveryRepairResult:
        stats = DeliveryRepairStats()
        current = list(placements)
        item_by_id = {item.item_id: item for item in items}
        cache = DeliveryBlockerCache.from_placements(item_by_id, current, self.settings)
        stats.initial_rehandles, stats.initial_violations = cache.score
        started = perf_counter()
        current, cache = self._scheduled_phase(
            current, cache, item_by_id, fixed_containers, validate_inherited,
            deadline=started + max(0.0, fixed_seconds), stats=stats,
            relocation_budget=self.relocation_transfer_max_candidates,
            swap_budget=self.swap_max_candidates,
            neighborhood_budget=self.neighborhood_max_candidates,
        )
        stats.fixed_phase_seconds = perf_counter() - started
        if not cache.edges and validate_final(current):
            stats.final_rehandles, stats.final_violations = cache.score
            stats.termination_reason = "valid_fixed_container"
            return DeliveryRepairResult(tuple(current), tuple(current), stats, False)

        if extra_seconds > 0 and extra_container is not None:
            extra_started = perf_counter()
            current, cache = self._scheduled_phase(
                current, cache, item_by_id, [extra_container, *fixed_containers], validate_inherited,
                deadline=extra_started + max(0.0, extra_seconds), stats=stats,
                relocation_budget=self.extra_max_candidates // 2,
                swap_budget=self.extra_max_candidates // 4,
                neighborhood_budget=self.extra_max_candidates - (
                    self.extra_max_candidates // 2 + self.extra_max_candidates // 4
                ),
            )
            stats.extra_phase_seconds = perf_counter() - extra_started
            if not cache.edges and validate_final(current):
                stats.final_rehandles, stats.final_violations = cache.score
                stats.termination_reason = "valid_with_one_extra_container"
                return DeliveryRepairResult(tuple(current), tuple(current), stats, True)

        stats.final_rehandles, stats.final_violations = cache.score
        if stats.candidates_evaluated >= self.max_candidates:
            stats.termination_reason = "operator_candidate_budgets_exhausted"
        elif stats.termination_reason == "not_started":
            stats.termination_reason = "local_optimum"
        return DeliveryRepairResult(None, tuple(current), stats, False)

    def _scheduled_phase(
        self, current: list[Placement], cache: DeliveryBlockerCache, item_by_id: dict[str, Item],
        containers: list[Container], validate_inherited: CandidateValidator, *, deadline: float,
        stats: DeliveryRepairStats, relocation_budget: int, swap_budget: int,
        neighborhood_budget: int,
    ) -> tuple[list[Placement], DeliveryBlockerCache]:
        """Run all operators with reserved independent candidate quotas."""
        seen: set[tuple[tuple[object, ...], ...]] = set()
        started = perf_counter()
        duration = max(0.0, deadline - started)
        relocation_deadline = started + duration * self.operator_time_fractions[0]
        swap_deadline = relocation_deadline + duration * self.operator_time_fractions[1]
        current, cache = self._relocate_transfer_phase(
            current, cache, item_by_id, containers, validate_inherited,
            deadline=min(deadline, relocation_deadline), stats=stats, seen=seen,
            phase_budget=max(0, relocation_budget),
        )
        if cache.edges and perf_counter() < min(deadline, swap_deadline):
            current, cache = self._swap_phase(
                current, cache, containers, item_by_id, validate_inherited, min(deadline, swap_deadline), stats,
                seen, max(0, swap_budget),
            )
        if cache.edges and perf_counter() < deadline:
            current, cache = self._neighborhood_phase(
                current, cache, item_by_id, containers, validate_inherited, deadline, stats,
                seen, max(0, neighborhood_budget),
            )
        return current, cache

    def _relocate_transfer_phase(
        self, current: list[Placement], cache: DeliveryBlockerCache, item_by_id: dict[str, Item],
        containers: list[Container], validate_inherited: CandidateValidator, *, deadline: float,
        stats: DeliveryRepairStats, seen: set[tuple[tuple[object, ...], ...]], phase_budget: int,
    ) -> tuple[list[Placement], DeliveryBlockerCache]:
        phase_start = stats.candidates_evaluated
        while (
            perf_counter() < deadline
            and stats.candidates_evaluated - phase_start < phase_budget
            and cache.edges
        ):
            closures = support_closures(current, self.support_epsilon)
            improved = False
            for item_id in cache.contributors(self.contributor_limit):
                if perf_counter() >= deadline or stats.candidates_evaluated - phase_start >= phase_budget:
                    break
                group_ids = closures.get(item_id, {item_id})
                moving = [value for value in current if value.item_id in group_ids]
                remaining = [value for value in current if value.item_id not in group_ids]
                root = next((value for value in moving if value.item_id == item_id), None)
                if root is None:
                    continue
                for target in containers:
                    state = _state(target, remaining, self.tolerance)
                    points = set(self.points.points(state, item_by_id[item_id], _dimensions(root)))
                    points.add((root.x_mm, root.y_mm, root.z_mm))
                    for point in sorted(points, key=lambda value: (value[2], value[1], value[0])):
                        if perf_counter() >= deadline or stats.candidates_evaluated - phase_start >= phase_budget:
                            break
                        delta = (point[0] - root.x_mm, point[1] - root.y_mm, point[2] - root.z_mm)
                        added = [
                            _shift(value, target.container_id, delta)
                            for value in sorted(moving, key=lambda value: (value.z_mm, value.item_id))
                        ]
                        stats.candidates_evaluated += 1
                        stats.partial_repack_candidates += int(len(added) > 1)
                        if len(added) == 1:
                            if target.container_id == root.container_id:
                                stats.relocation_candidates += 1
                            else:
                                stats.transfer_candidates += 1
                        if not _allows_group(state, added, self.policy, self.tolerance):
                            continue
                        candidate = [*remaining, *added]
                        signature = _signature(candidate)
                        if signature in seen:
                            continue
                        seen.add(signature)
                        candidate_cache = cache.changed(remaining, added)
                        if candidate_cache.score >= cache.score:
                            continue
                        stats.improving_candidates_validated += 1
                        if not validate_inherited(candidate):
                            continue
                        current, cache = candidate, candidate_cache
                        stats.accepted_moves.append(
                            "partial_repack" if len(added) > 1 else
                            "relocate" if target.container_id == root.container_id else "transfer"
                        )
                        improved = True
                        break
                    if improved:
                        break
                if improved:
                    break
            if not improved:
                break
        return current, cache

    def _swap_phase(
        self, current: list[Placement], cache: DeliveryBlockerCache, containers: list[Container],
        item_by_id: dict[str, Item], validate_inherited: CandidateValidator, deadline: float,
        stats: DeliveryRepairStats, seen: set[tuple[tuple[object, ...], ...]], phase_budget: int,
    ) -> tuple[list[Placement], DeliveryBlockerCache]:
        phase_start = stats.candidates_evaluated
        while perf_counter() < deadline and stats.candidates_evaluated - phase_start < phase_budget and cache.edges:
            closures = support_closures(current, self.support_epsilon)
            swapped = self._try_swap(
                current, cache, containers, item_by_id, closures, validate_inherited, deadline,
                stats, seen, phase_start + phase_budget,
            )
            if swapped is None:
                break
            current, cache = swapped
        return current, cache

    def _neighborhood_phase(
        self, current: list[Placement], cache: DeliveryBlockerCache, item_by_id: dict[str, Item],
        containers: list[Container], validate_inherited: CandidateValidator, deadline: float,
        stats: DeliveryRepairStats, seen: set[tuple[tuple[object, ...], ...]], phase_budget: int,
    ) -> tuple[list[Placement], DeliveryBlockerCache]:
        """Destroy and greedily reinsert a small conflict-root neighborhood."""
        phase_start = stats.candidates_evaluated
        for size in self.neighborhood_sizes:
            if perf_counter() >= deadline or stats.candidates_evaluated - phase_start >= phase_budget or not cache.edges:
                break
            closures = support_closures(current, self.support_epsilon)
            groups = _conflict_groups(current, cache, closures, size)
            if len(groups) < 2:
                continue
            stats.neighborhood_attempts += 1
            removed_ids = {value.item_id for group in groups for value in group}
            working = [value for value in current if value.item_id not in removed_ids]
            working_cache = DeliveryBlockerCache.from_placements(item_by_id, working, self.settings)
            feasible = True
            for group in sorted(groups, key=lambda values: (_priority(item_by_id[values[0].item_id]), values[0].item_id)):
                root = group[0]
                best: tuple[tuple[int, int, float, float, float], list[Placement], DeliveryBlockerCache] | None = None
                for container in containers:
                    state = _state(container, working, self.tolerance)
                    points = self.points.points(state, item_by_id[root.item_id], _dimensions(root))[:12]
                    for point in points:
                        if perf_counter() >= deadline or stats.candidates_evaluated - phase_start >= phase_budget:
                            feasible = False
                            break
                        delta = (point[0] - root.x_mm, point[1] - root.y_mm, point[2] - root.z_mm)
                        added = [_shift(value, container.container_id, delta) for value in group]
                        stats.candidates_evaluated += 1
                        stats.neighborhood_candidates += 1
                        stats.partial_repack_candidates += 1
                        if not _allows_group(state, added, self.policy, self.tolerance):
                            continue
                        trial_cache = working_cache.changed(working, added)
                        rank = (*trial_cache.score, point[2], point[1], point[0])
                        if best is None or rank < best[0]:
                            best = rank, added, trial_cache
                    if not feasible:
                        break
                if not feasible or best is None:
                    feasible = False
                    break
                working.extend(best[1])
                working_cache = best[2]
            if not feasible or working_cache.score >= cache.score:
                continue
            signature = _signature(working)
            if signature in seen:
                continue
            seen.add(signature)
            stats.improving_candidates_validated += 1
            if not validate_inherited(working):
                continue
            stats.accepted_moves.append("conflict_neighborhood_reinsert")
            return working, working_cache
        return current, cache

    def _try_swap(
        self, current: list[Placement], cache: DeliveryBlockerCache, containers: list[Container],
        item_by_id: dict[str, Item], closures: dict[str, set[str]], validate_inherited: CandidateValidator,
        deadline: float, stats: DeliveryRepairStats, seen: set[tuple[tuple[object, ...], ...]],
        phase_candidate_limit: int,
    ) -> tuple[list[Placement], DeliveryBlockerCache] | None:
        leaves = [value for value in current if len(closures.get(value.item_id, ())) == 1]
        source_ids = set(cache.contributors(self.contributor_limit))
        for left in sorted((value for value in leaves if value.item_id in source_ids), key=lambda value: value.item_id):
            for right in sorted(leaves, key=lambda value: (value.container_id, value.z_mm, value.y_mm, value.x_mm, value.item_id)):
                if left.item_id == right.item_id or perf_counter() >= deadline or stats.candidates_evaluated >= phase_candidate_limit:
                    return None
                remaining = [value for value in current if value.item_id not in {left.item_id, right.item_id}]
                left_new = _at_origin(left, right)
                right_new = _at_origin(right, left)
                states = {container.container_id: _state(container, remaining, self.tolerance) for container in containers if container.container_id in {left_new.container_id, right_new.container_id}}
                stats.candidates_evaluated += 1
                stats.swap_candidates += 1
                if any(not _allows_group(states[value.container_id], [value], self.policy, self.tolerance) for value in (left_new, right_new)):
                    continue
                candidate = [*remaining, left_new, right_new]
                signature = _signature(candidate)
                if signature in seen:
                    continue
                seen.add(signature)
                candidate_cache = cache.changed(remaining, [left_new, right_new])
                if candidate_cache.score >= cache.score:
                    continue
                stats.improving_candidates_validated += 1
                if not validate_inherited(candidate):
                    continue
                stats.accepted_moves.append("swap")
                return candidate, candidate_cache
        return None


def _edges(items_by_id: dict[str, Item], placements: list[Placement], settings: UnloadingSettings) -> set[tuple[str, str]]:
    return {
        (target.item_id, blocker.item_id)
        for target in placements for blocker in placements
        if is_later_priority_direct_blocker(items_by_id, target, blocker, settings)
    }


def _conflict_groups(
    placements: list[Placement], cache: DeliveryBlockerCache,
    closures: dict[str, set[str]], size: int,
) -> list[list[Placement]]:
    by_id = {value.item_id: value for value in placements}
    selected: list[list[Placement]] = []
    selected_ids: set[str] = set()
    for item_id in cache.contributors(max(size * 3, size)):
        group_ids = closures.get(item_id, {item_id})
        if group_ids & selected_ids:
            continue
        group = sorted(
            (by_id[value] for value in group_ids),
            key=lambda value: (value.z_mm, value.item_id),
        )
        selected.append(group)
        selected_ids.update(group_ids)
        if len(selected) >= size:
            break
    return selected


def _priority(item: Item) -> int:
    return int(str(item.source["delivery_priority"]))


def _at_origin(item: Placement, origin: Placement) -> Placement:
    return Placement(
        item.item_id, origin.container_id, origin.x_mm, origin.y_mm, origin.z_mm,
        item.length_mm, item.width_mm, item.height_mm, item.weight_kg, item.orientation_code,
    )


def _signature(placements: list[Placement]) -> tuple[tuple[object, ...], ...]:
    return tuple(sorted(
        (value.item_id, value.container_id, value.x_mm, value.y_mm, value.z_mm,
         value.length_mm, value.width_mm, value.height_mm)
        for value in placements
    ))
