"""Bounded conflict-neighborhood search for closing a used Level 8 container."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Callable

from ..algorithms.feasibility import PlacementFeasibilityPolicy
from ..schemas import Container, Item, Placement
from .center_of_mass import evaluate_center_of_mass
from .level_07_balance_repair import _allows_group, _dimensions, _shift, _state
from .level_08_delivery_repair import DeliveryBlockerCache
from .level_08_delivery_scoring import DeliveryDoorPointProvider
from .unloading import UnloadingSettings
from ..geometry.support import evaluate_support


CandidateValidator = Callable[[list[Placement]], bool]


@dataclass(frozen=True)
class ContainerEliminationLnsResult:
    placements: tuple[Placement, ...] | None
    attempts: int
    candidates_evaluated: int
    neighborhoods_evaluated: int
    selected_neighborhood_size: int | None
    termination_reason: str


class DeliveryContainerEliminationLns:
    """Destroy receiver support components and reinsert them with donor cargo.

    Search never opens a container: every candidate is restricted to the used
    containers other than the donor. Support-connected components are moved as
    rigid groups so a supporter is never left behind without its dependents.
    """

    def __init__(
        self, *, policy: PlacementFeasibilityPolicy,
        unloading_settings: UnloadingSettings, balance_config: dict,
        tolerance_mm: float, support_epsilon_mm: float,
        neighborhood_sizes: tuple[int, ...] = (4, 8, 12),
        max_candidates: int = 2048, points_per_group: int = 24,
    ) -> None:
        if max_candidates <= 0 or points_per_group <= 0:
            raise ValueError("Container-elimination LNS budgets must be positive")
        sizes = tuple(sorted({value for value in neighborhood_sizes if value > 0}))
        if not sizes:
            raise ValueError("Container-elimination LNS requires a positive neighborhood size")
        self.policy = policy
        self.unloading_settings = unloading_settings
        self.balance_config = balance_config
        self.tolerance = tolerance_mm
        self.support_epsilon = support_epsilon_mm
        self.neighborhood_sizes = sizes
        self.max_candidates = max_candidates
        self.points_per_group = points_per_group
        self.points = DeliveryDoorPointProvider(unloading_settings, balance_config)

    def eliminate(
        self, items: list[Item], containers: list[Container],
        placements: list[Placement], *, donor_ids: list[str],
        validate_final: CandidateValidator, deadline: float,
    ) -> ContainerEliminationLnsResult:
        item_by_id = {value.item_id: value for value in items}
        attempts = candidates = neighborhoods = 0
        for donor_id in donor_ids:
            if perf_counter() >= deadline:
                return ContainerEliminationLnsResult(
                    None, attempts, candidates, neighborhoods, None, "time_limit"
                )
            donor_groups = [
                group for group in _support_components(placements, self.support_epsilon)
                if group[0].container_id == donor_id
            ]
            if not donor_groups:
                continue
            targets = [value for value in containers if value.container_id != donor_id]
            receiver_groups = [
                group for group in _support_components(placements, self.support_epsilon)
                if group[0].container_id != donor_id
            ]
            receiver_groups.sort(key=lambda value: (-_group_volume(value), value[0].item_id))
            for size in self.neighborhood_sizes:
                if perf_counter() >= deadline or candidates >= self.max_candidates:
                    reason = "time_limit" if perf_counter() >= deadline else "candidate_limit"
                    return ContainerEliminationLnsResult(
                        None, attempts, candidates, neighborhoods, None, reason
                    )
                attempts += 1
                neighborhoods += 1
                destroyed = [*donor_groups, *receiver_groups[:size]]
                removed_ids = {value.item_id for group in destroyed for value in group}
                working = [value for value in placements if value.item_id not in removed_ids]
                ordered_groups = sorted(
                    destroyed,
                    key=lambda group: (
                        -max(_priority(item_by_id[value.item_id]) for value in group),
                        -_group_volume(group),
                        group[0].item_id,
                    ),
                )
                feasible = True
                for group in ordered_groups:
                    root = group[0]
                    best: tuple[tuple[float, ...], list[Placement]] | None = None
                    for container_rank, target in enumerate(targets):
                        state = _state(target, working, self.tolerance)
                        for point in self.points.points(
                            state, item_by_id[root.item_id], _dimensions(root)
                        )[: self.points_per_group]:
                            if perf_counter() >= deadline or candidates >= self.max_candidates:
                                feasible = False
                                break
                            delta = (
                                point[0] - root.x_mm,
                                point[1] - root.y_mm,
                                point[2] - root.z_mm,
                            )
                            added = [
                                _shift(value, target.container_id, delta)
                                for value in group
                            ]
                            candidates += 1
                            if not _allows_group(
                                state, added, self.policy, self.tolerance
                            ):
                                continue
                            trial = [*working, *added]
                            blocker_score = DeliveryBlockerCache.from_placements(
                                item_by_id, trial, self.unloading_settings
                            ).score
                            cog = evaluate_center_of_mass(
                                [
                                    value for value in trial
                                    if value.container_id == target.container_id
                                ],
                                [target],
                                self.balance_config,
                                tolerance=self.tolerance,
                            ).records[0]
                            cog_violation = max(
                                0.0,
                                cog.absolute_longitudinal_offset_ratio
                                - cog.max_longitudinal_offset_ratio,
                            ) + max(
                                0.0,
                                cog.absolute_lateral_offset_ratio
                                - cog.max_lateral_offset_ratio,
                            )
                            rank = (
                                float(blocker_score[0]),
                                float(blocker_score[1]),
                                cog_violation,
                                cog.absolute_longitudinal_offset_ratio
                                + cog.absolute_lateral_offset_ratio,
                                float(container_rank),
                                float(point[2]), float(point[1]), float(point[0]),
                            )
                            if best is None or rank < best[0]:
                                best = rank, added
                        if not feasible:
                            break
                    if not feasible or best is None:
                        feasible = False
                        break
                    working.extend(best[1])
                if (
                    feasible
                    and not any(value.container_id == donor_id for value in working)
                    and validate_final(working)
                ):
                    return ContainerEliminationLnsResult(
                        tuple(working), attempts, candidates, neighborhoods,
                        size, "container_eliminated"
                    )
        return ContainerEliminationLnsResult(
            None, attempts, candidates, neighborhoods, None,
            "time_limit" if perf_counter() >= deadline else
            "candidate_limit" if candidates >= self.max_candidates else
            "no_valid_elimination",
        )


def _support_components(
    placements: list[Placement], epsilon_mm: float,
) -> list[list[Placement]]:
    """Return deterministic weak components of the direct support graph."""
    by_id = {value.item_id: value for value in placements}
    adjacency = {value.item_id: set() for value in placements}
    for child in placements:
        support = evaluate_support(child, placements, epsilon_mm=epsilon_mm)
        for parent_id in support.supporting_item_ids:
            adjacency[child.item_id].add(parent_id)
            adjacency[parent_id].add(child.item_id)
    components: list[list[Placement]] = []
    unseen = set(by_id)
    while unseen:
        start = min(unseen)
        pending = [start]
        component: set[str] = set()
        while pending:
            current = pending.pop()
            if current in component:
                continue
            component.add(current)
            pending.extend(sorted(adjacency[current] - component, reverse=True))
        unseen -= component
        components.append(sorted(
            (by_id[value] for value in component),
            key=lambda value: (value.z_mm, value.y_mm, value.x_mm, value.item_id),
        ))
    return sorted(
        components,
        key=lambda group: (group[0].container_id, group[0].item_id),
    )


def _group_volume(group: list[Placement]) -> float:
    return sum(
        value.length_mm * value.width_mm * value.height_mm for value in group
    )


def _priority(item: Item) -> int:
    return int(str(item.source["delivery_priority"]))
