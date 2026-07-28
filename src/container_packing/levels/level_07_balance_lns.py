"""Bounded large-neighborhood balance repair for Level 7 compound roots.

The engine never rebuilds the full solution.  It removes a small set of leaf
compound roots from the containers with the worst COG evidence, then repacks
only that neighborhood into the already open containers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Callable

from ..algorithms.feasibility import PlacementFeasibilityPolicy
from ..algorithms.heuristics.extreme_point_core import candidate_placement
from ..schemas import Container, Item, Placement
from .level_07_balance_points import BalanceAnchorPointProvider
from .level_07_balance_repair import (
    BalanceMomentCache,
    RootMassProperties,
    _dimensions,
    _allows_group,
    _ranking,
    _shift,
    _state,
    _used_container_count,
    support_closures,
)
from .load_balance import resolve_container_balance_attributes


CandidateValidator = Callable[[list[Placement]], bool]
Clock = Callable[[], float]


@dataclass
class BalanceLnsStats:
    rounds_attempted: int = 0
    candidates_evaluated: int = 0
    neighborhoods_attempted: int = 0
    accepted_round: int | None = None
    affected_container_ids: list[str] = field(default_factory=list)
    destroyed_item_ids: list[str] = field(default_factory=list)
    runtime_seconds: float = 0.0
    termination_reason: str = "not_started"
    neighborhood_sizes_attempted: list[int] = field(default_factory=list)
    duplicate_candidates_skipped: int = 0
    initial_max_violation: float = 0.0
    final_max_violation: float = 0.0

    def metadata(self) -> dict[str, object]:
        return {
            "balance_lns_rounds_attempted": self.rounds_attempted,
            "balance_lns_candidates_evaluated": self.candidates_evaluated,
            "balance_lns_neighborhoods_attempted": self.neighborhoods_attempted,
            "balance_lns_accepted_round": self.accepted_round,
            "balance_lns_affected_container_ids": list(self.affected_container_ids),
            "balance_lns_destroyed_item_ids": list(self.destroyed_item_ids),
            "balance_lns_runtime_seconds": self.runtime_seconds,
            "balance_lns_termination_reason": self.termination_reason,
            "balance_lns_donor_selection": "opposite_signed_cog_offset_v1",
            "balance_lns_neighborhood_selection": "directional_moment_contribution_v1",
            "balance_lns_neighborhood_sizes_attempted": list(
                self.neighborhood_sizes_attempted
            ),
            "balance_lns_duplicate_candidates_skipped": self.duplicate_candidates_skipped,
            "balance_lns_initial_max_violation": self.initial_max_violation,
            "balance_lns_final_max_violation": self.final_max_violation,
        }


@dataclass(frozen=True)
class BalanceLnsResult:
    placements: tuple[Placement, ...] | None
    best_feasible_placements: tuple[Placement, ...]
    stats: BalanceLnsStats


class BalanceLnsEngine:
    """Deterministic destroy/repack search restricted to affected containers."""

    def __init__(
        self, *, policy: PlacementFeasibilityPolicy, balance_config: dict,
        coordinate_tolerance_mm: float, support_epsilon_mm: float,
        max_candidates: int, neighborhood_size: int,
        affected_container_limit: int, max_rounds: int,
        mass_properties: dict[str, RootMassProperties] | None = None,
        neighborhood_sizes: tuple[int, ...] | None = None,
        clock: Clock = perf_counter,
    ) -> None:
        if max_candidates <= 0 or neighborhood_size <= 1:
            raise ValueError("LNS candidate budget must be positive and neighborhood_size > 1")
        self.policy = policy
        self.balance_config = balance_config
        self.tolerance = coordinate_tolerance_mm
        self.support_epsilon = support_epsilon_mm
        self.max_candidates = max_candidates
        self.neighborhood_sizes = tuple(
            sorted(set(neighborhood_sizes or (neighborhood_size,)))
        )
        if any(value <= 1 for value in self.neighborhood_sizes):
            raise ValueError("Every LNS neighborhood size must be greater than 1")
        self.affected_container_limit = affected_container_limit
        self.max_rounds = max_rounds
        self.mass_properties = dict(mass_properties or {})
        self.anchor_provider = BalanceAnchorPointProvider(balance_config)
        self.clock = clock

    def repair(
        self, items: list[Item], containers: list[Container], placements: list[Placement],
        *, validate_candidate: CandidateValidator, time_limit_seconds: float,
        validate_final_candidate: CandidateValidator | None = None,
    ) -> BalanceLnsResult:
        validate_final = validate_final_candidate or validate_candidate
        started = self.clock()
        deadline = started + max(0.0, time_limit_seconds)
        stats = BalanceLnsStats()
        container_map = {value.container_id: value for value in containers}
        initial_count = _used_container_count(placements)
        current = list(placements)
        initial_moments = BalanceMomentCache.from_placements(current, self.mass_properties)
        current_score = _ranking(initial_moments, current, container_map, self.balance_config)
        stats.initial_max_violation = current_score[0]
        stats.final_max_violation = current_score[0]

        by_id = {value.item_id: value for value in items}
        seen_signatures: set[tuple[tuple[object, ...], ...]] = set()
        for neighborhood_size in self.neighborhood_sizes:
            if self.clock() >= deadline or stats.candidates_evaluated >= self.max_candidates:
                break
            affected = _affected_containers(
                current, containers, self.balance_config, self.mass_properties,
                self.affected_container_limit,
            )
            for value in affected:
                if value.container_id not in stats.affected_container_ids:
                    stats.affected_container_ids.append(value.container_id)
            closures = support_closures(current, self.support_epsilon)
            if not affected:
                break
            neighborhood = _closure_neighborhood(
                current, closures, affected, self.mass_properties,
                self.balance_config, neighborhood_size,
            )
            if len(neighborhood) < 2:
                continue
            stats.neighborhood_sizes_attempted.append(neighborhood_size)
            stats.destroyed_item_ids.extend(
                value.item_id for group in neighborhood for value in group
                if value.item_id not in stats.destroyed_item_ids
            )
            for round_index in range(self.max_rounds):
                if self.clock() >= deadline or stats.candidates_evaluated >= self.max_candidates:
                    break
                stats.rounds_attempted += 1
                stats.neighborhoods_attempted += 1
                ordered = sorted(
                    neighborhood,
                    key=lambda group: (
                        -sum(value.weight_kg for value in group), group[0].item_id
                    ),
                    reverse=bool(round_index % 2),
                )
                candidate = self._repack(
                    ordered, affected, current, by_id, container_map,
                    deadline, stats, seen_signatures,
                )
                if candidate is None or _used_container_count(candidate) != initial_count:
                    continue
                moments = BalanceMomentCache.from_placements(
                    candidate, self.mass_properties
                )
                score = _ranking(
                    moments, candidate, container_map, self.balance_config
                )
                if score >= current_score or not validate_candidate(candidate):
                    continue
                stats.accepted_round = round_index
                current = candidate
                current_score = score
                stats.final_max_violation = current_score[0]
                if current_score[0] <= 1e-12 and validate_final(current):
                    stats.termination_reason = "accepted_valid_neighborhood"
                    stats.runtime_seconds = self.clock() - started
                    resolved = tuple(current)
                    return BalanceLnsResult(resolved, resolved, stats)

        stats.runtime_seconds = self.clock() - started
        stats.termination_reason = (
            "candidate_limit" if stats.candidates_evaluated >= self.max_candidates
            else "deadline" if self.clock() >= deadline
            else "no_repackable_neighborhood" if not stats.neighborhoods_attempted
            else "no_improving_valid_neighborhood"
        )
        stats.final_max_violation = current_score[0]
        return BalanceLnsResult(None, tuple(current), stats)

    def _repack(
        self, removed: list[list[Placement]], affected: list[Container],
        original: list[Placement], item_by_id: dict[str, Item],
        container_map: dict[str, Container], deadline: float, stats: BalanceLnsStats,
        seen_signatures: set[tuple[tuple[object, ...], ...]],
    ) -> list[Placement] | None:
        removed_ids = {value.item_id for group in removed for value in group}
        working = [value for value in original if value.item_id not in removed_ids]
        moments = BalanceMomentCache.from_placements(working, self.mass_properties)
        for group in removed:
            original_root = group[0]
            if self.clock() >= deadline or stats.candidates_evaluated >= self.max_candidates:
                return None
            best: tuple[tuple[float, ...], Placement] | None = None
            for container in affected:
                state = _state(container, working, self.tolerance)
                points = self.anchor_provider.points(
                    state, item_by_id[original_root.item_id], _dimensions(original_root)
                )
                # A small deterministic point cap prevents one root consuming the LNS budget.
                for point in points[:12]:
                    if self.clock() >= deadline or stats.candidates_evaluated >= self.max_candidates:
                        return None
                    candidate_root = candidate_placement(
                        state, item_by_id[original_root.item_id], point,
                        _dimensions(original_root),
                    )
                    stats.candidates_evaluated += 1
                    delta = (
                        candidate_root.x_mm - original_root.x_mm,
                        candidate_root.y_mm - original_root.y_mm,
                        candidate_root.z_mm - original_root.z_mm,
                    )
                    added = [
                        _shift(value, container.container_id, delta)
                        for value in sorted(group, key=lambda value: (value.z_mm, value.item_id))
                    ]
                    if not _allows_group(state, added, self.policy, self.tolerance):
                        continue
                    trial = [*working, *added]
                    signature = _placement_signature(trial)
                    if signature in seen_signatures:
                        stats.duplicate_candidates_skipped += 1
                        continue
                    seen_signatures.add(signature)
                    trial_moments = moments.changed([], added)
                    score = _ranking(trial_moments, trial, container_map, self.balance_config)
                    if best is None or score < best[0]:
                        best = score, added
            if best is None:
                return None
            working.extend(best[1])
            moments = moments.changed([], best[1])
        return working


def _affected_containers(
    placements: list[Placement], containers: list[Container], balance_config: dict,
    mass_properties: dict[str, RootMassProperties], limit: int,
) -> list[Container]:
    container_map = {value.container_id: value for value in containers}
    attributes = resolve_container_balance_attributes(containers, balance_config)
    moments = BalanceMomentCache.from_placements(placements, mass_properties)
    records: list[tuple[float, float, float, str]] = []
    for container_id, (mass, moment_x, moment_y) in moments.values.items():
        if mass <= 1e-9:
            continue
        container = container_map[container_id]
        attr = attributes[container_id]
        signed_x = moment_x / mass / container.length_mm - attr.target_longitudinal_ratio
        signed_y = moment_y / mass / container.width_mm - attr.target_lateral_ratio
        violation = max(0.0, abs(signed_x) - attr.max_longitudinal_offset_ratio)
        violation += max(0.0, abs(signed_y) - attr.max_lateral_offset_ratio)
        records.append((violation, signed_x, signed_y, container_id))
    violating = sorted(
        (value for value in records if value[0] > 0),
        key=lambda value: (-value[0], value[3]),
    )
    selected = list(violating[:limit])
    if selected and len(selected) < limit:
        worst = selected[0]
        donors = [value for value in records if value[3] not in {row[3] for row in selected}]
        donors.sort(key=lambda value: (
            worst[1] * value[1] + worst[2] * value[2], value[3]
        ))
        selected.extend(donors[:limit - len(selected)])
    return [container_map[value[3]] for value in selected]


def _closure_neighborhood(
    placements: list[Placement], closures: dict[str, set[str]],
    affected: list[Container], mass_properties: dict[str, RootMassProperties],
    balance_config: dict, size: int,
) -> list[list[Placement]]:
    affected_ids = {value.container_id for value in affected}
    container_rank = {value.container_id: index for index, value in enumerate(affected)}
    attributes = resolve_container_balance_attributes(affected, balance_config)
    moments = BalanceMomentCache.from_placements(placements, mass_properties)
    dominant: dict[str, tuple[str, float, float]] = {}
    for container in affected:
        mass, moment_x, moment_y = moments.values.get(
            container.container_id, [0.0, 0.0, 0.0]
        )
        if mass <= 1e-9:
            continue
        attr = attributes[container.container_id]
        signed_x = moment_x / mass / container.length_mm - attr.target_longitudinal_ratio
        signed_y = moment_y / mass / container.width_mm - attr.target_lateral_ratio
        excess_x = max(0.0, abs(signed_x) - attr.max_longitudinal_offset_ratio)
        excess_y = max(0.0, abs(signed_y) - attr.max_lateral_offset_ratio)
        if excess_y > excess_x:
            dominant[container.container_id] = (
                "y", signed_y, attr.target_lateral_ratio * container.width_mm
            )
        else:
            dominant[container.container_id] = (
                "x", signed_x, attr.target_longitudinal_ratio * container.length_mm
            )
    candidates = [
        value for value in placements
        if value.container_id in affected_ids
    ]
    def priority(value: Placement) -> tuple[int, float, float, float, str]:
        properties = mass_properties.get(
            value.item_id,
            RootMassProperties(
                value.weight_kg, value.length_mm / 2.0, value.width_mm / 2.0
            ),
        )
        axis, signed_offset, target_mm = dominant.get(
            value.container_id, ("y", 0.0, 0.0)
        )
        center_mm = (
            value.y_mm + properties.center_offset_y_mm
            if axis == "y"
            else value.x_mm + properties.center_offset_x_mm
        )
        item_signed_offset = center_mm - target_mm
        directional_contribution = (
            properties.mass_kg * abs(item_signed_offset)
            if signed_offset * item_signed_offset > 0.0 else 0.0
        )
        return (
            container_rank[value.container_id],
            -directional_contribution,
            -properties.mass_kg,
            -value.z_mm,
            value.item_id,
        )
    selected: list[list[Placement]] = []
    selected_ids: set[str] = set()
    for root in sorted(candidates, key=priority):
        group_ids = closures[root.item_id]
        if group_ids & selected_ids:
            continue
        group = [value for value in placements if value.item_id in group_ids]
        selected.append(sorted(group, key=lambda value: (value.z_mm, value.item_id)))
        selected_ids.update(group_ids)
        if len(selected) >= size:
            break
    return selected


def _placement_signature(
    placements: list[Placement],
) -> tuple[tuple[object, ...], ...]:
    return tuple(sorted(
        (
            value.item_id, value.container_id,
            round(value.x_mm, 6), round(value.y_mm, 6), round(value.z_mm, 6),
            value.orientation_code,
        )
        for value in placements
    ))
