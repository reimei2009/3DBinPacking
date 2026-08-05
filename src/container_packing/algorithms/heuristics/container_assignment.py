"""Deterministic fixed-subset construction guidance with soft stop affinity."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from time import perf_counter
from typing import Mapping, Protocol

from ...schemas import Container, Item, Placement


@dataclass(frozen=True)
class ContainerAffinity:
    """Ranked container preferences shared by every item in one order group."""

    group_id: str
    stop_id: str
    item_ids: tuple[str, ...]
    ranked_container_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.group_id or not self.stop_id:
            raise ValueError("Container affinity group_id and stop_id must not be empty")
        if not self.item_ids or len(self.item_ids) != len(set(self.item_ids)):
            raise ValueError("Container affinity requires unique item IDs")
        if (
            not self.ranked_container_ids
            or len(self.ranked_container_ids) != len(set(self.ranked_container_ids))
        ):
            raise ValueError("Container affinity requires unique ranked container IDs")


@dataclass(frozen=True)
class ContainerAffinityPlan:
    """One fixed subset plus soft container affinities for all order groups."""

    container_subset_ids: tuple[str, ...]
    affinities: tuple[ContainerAffinity, ...]
    score: tuple[object, ...]
    planned_used_container_count: int
    planned_stop_fragmentation: int
    total_cost: float
    maximum_utilization: float
    utilization_imbalance: float

    def __post_init__(self) -> None:
        if (
            not self.container_subset_ids
            or len(self.container_subset_ids) != len(set(self.container_subset_ids))
        ):
            raise ValueError("Container assignment plan requires a unique fixed subset")
        groups = [value.group_id for value in self.affinities]
        if len(groups) != len(set(groups)):
            raise ValueError("Container assignment plan contains duplicate groups")
        item_ids = [item_id for value in self.affinities for item_id in value.item_ids]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("Container assignment plan contains duplicate item IDs")
        subset = set(self.container_subset_ids)
        for affinity in self.affinities:
            if set(affinity.ranked_container_ids) != subset:
                raise ValueError(
                    f"Affinity {affinity.group_id} must rank every fixed-subset container exactly once"
                )

    @property
    def signature(self) -> tuple[tuple[str, str, tuple[str, ...]], ...]:
        return tuple(
            (value.group_id, value.stop_id, value.ranked_container_ids)
            for value in self.affinities
        )

    @property
    def by_item_id(self) -> dict[str, ContainerAffinity]:
        return {
            item_id: affinity
            for affinity in self.affinities
            for item_id in affinity.item_ids
        }

    def metadata(self) -> dict[str, object]:
        return {
            "container_assignment_mode": "fixed_subset_soft_stop_affinity_v1",
            "container_assignment_subset_ids": list(self.container_subset_ids),
            "container_assignment_group_count": len(self.affinities),
            "container_assignment_planned_used_count": self.planned_used_container_count,
            "container_assignment_planned_stop_fragmentation": self.planned_stop_fragmentation,
            "container_assignment_total_cost": self.total_cost,
            "container_assignment_maximum_utilization": self.maximum_utilization,
            "container_assignment_utilization_imbalance": self.utilization_imbalance,
            "container_assignment_signature": [
                [group_id, stop_id, list(container_ids)]
                for group_id, stop_id, container_ids in self.signature
            ],
        }


class ContainerAssignmentPlanner(Protocol):
    """Generate cardinality-aware affinity plans for one container subset."""

    planner_id: str

    def plans(
        self, containers: tuple[Container, ...], items: list[Item], *,
        deadline_monotonic: float | None = None,
    ) -> tuple[ContainerAffinityPlan, ...]: ...

    def metadata(self) -> dict[str, object]: ...


@dataclass
class ContainerPreferencePolicy:
    """Apply fixed-subset soft affinity and atomic declared orders."""

    plan: ContainerAffinityPlan
    policy_id: str = "fixed_subset_soft_stop_affinity_v1"
    candidates_ranked: int = 0
    bound_container_by_group: dict[str, str] = field(default_factory=dict)
    _by_item_id: dict[str, ContainerAffinity] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._by_item_id = self.plan.by_item_id

    def allows(self, item: Item, container_id: str) -> bool:
        """Keep a declared multi-item order together after its first placement."""
        affinity = self._affinity(item.item_id)
        if container_id not in affinity.ranked_container_ids:
            return False
        bound = self.bound_container_by_group.get(affinity.group_id)
        return bound is None or bound == container_id

    def rank(self, item: Item, container_id: str) -> int:
        affinity = self._affinity(item.item_id)
        try:
            result = affinity.ranked_container_ids.index(container_id)
        except ValueError as exc:
            raise ValueError(
                f"Container {container_id} is outside fixed subset for item {item.item_id}"
            ) from exc
        self.candidates_ranked += 1
        return result

    def record_selection(self, item: Item, container_id: str) -> None:
        affinity = self._affinity(item.item_id)
        current = self.bound_container_by_group.setdefault(
            affinity.group_id, container_id
        )
        if current != container_id:
            raise RuntimeError(
                f"Order group {affinity.group_id} was split across containers"
            )

    def metadata(self, placements: list[Placement]) -> dict[str, object]:
        selected = {value.item_id: value.container_id for value in placements}
        preferred_hits = 0
        fallback_count = 0
        actual_stop_containers: dict[str, set[str]] = {}
        actual_used: set[str] = set()
        for item_id, container_id in selected.items():
            affinity = self._affinity(item_id)
            actual_used.add(container_id)
            if affinity.ranked_container_ids[0] == container_id:
                preferred_hits += 1
            else:
                fallback_count += 1
        for affinity in self.plan.affinities:
            group_containers = {
                selected[item_id]
                for item_id in affinity.item_ids
                if item_id in selected
            }
            actual_stop_containers.setdefault(
                affinity.stop_id, set()
            ).update(group_containers)
        actual_fragmentation = sum(
            max(0, len(values) - 1) for values in actual_stop_containers.values()
        )
        return {
            **self.plan.metadata(),
            "container_preference_policy": self.policy_id,
            "container_affinity_candidates_ranked": self.candidates_ranked,
            "container_affinity_preferred_hits": preferred_hits,
            "container_affinity_fallback_count": fallback_count,
            "container_affinity_groups_moved_from_first_preference": sum(
                1
                for affinity in self.plan.affinities
                if any(
                    selected.get(item_id) not in {None, affinity.ranked_container_ids[0]}
                    for item_id in affinity.item_ids
                )
            ),
            "container_assignment_actual_used_count": len(actual_used),
            "container_assignment_actual_stop_fragmentation": actual_fragmentation,
        }

    def _affinity(self, item_id: str) -> ContainerAffinity:
        try:
            return self._by_item_id[item_id]
        except KeyError as exc:
            raise ValueError(
                f"Container affinity plan is missing item {item_id}"
            ) from exc


@dataclass(frozen=True)
class _AssignmentGroup:
    group_id: str
    item_ids: tuple[str, ...]
    stop_id: str
    priority: int
    weight_kg: float
    volume_m3: float
    items: tuple[Item, ...]


@dataclass(frozen=True)
class _BeamState:
    assignments: tuple[tuple[str, str], ...] = ()
    loaded_weight: tuple[tuple[str, float], ...] = ()
    loaded_volume: tuple[tuple[str, float], ...] = ()
    stop_containers: tuple[tuple[str, tuple[str, ...]], ...] = ()


@dataclass
class StopAwareBeamAssignmentPlanner:
    """Create fixed-subset order affinities with bounded deterministic beam search."""

    beam_width: int = 32
    max_plans_per_subset: int = 16
    utilization_target: float = 0.85
    planner_id: str = "hierarchical_stop_aware_soft_affinity_v1"
    subsets_evaluated: int = 0
    states_generated: int = 0
    states_capacity_pruned: int = 0
    states_fit_pruned: int = 0
    plans_generated: int = 0
    deadline_reached: bool = False
    termination_reason: str = "not_started"

    def __post_init__(self) -> None:
        if self.beam_width <= 0 or self.max_plans_per_subset <= 0:
            raise ValueError("Stop-aware beam budgets must be positive")
        if not 0.0 < self.utilization_target <= 1.0:
            raise ValueError("Assignment utilization_target must be in (0, 1]")

    def plans(
        self, containers: tuple[Container, ...], items: list[Item], *,
        deadline_monotonic: float | None = None,
    ) -> tuple[ContainerAffinityPlan, ...]:
        if deadline_monotonic is not None and not isfinite(deadline_monotonic):
            raise ValueError("Assignment deadline must be finite")
        if not containers:
            raise ValueError("Stop-aware assignment requires a non-empty fixed subset")
        self.subsets_evaluated += 1
        self.termination_reason = "searching"
        container_map = {value.container_id: value for value in containers}
        groups = _assignment_groups(items)
        beam = [_BeamState()]
        for group in groups:
            if _deadline_reached(deadline_monotonic):
                self.deadline_reached = True
                self.termination_reason = "deadline_reached"
                return ()
            next_states: dict[tuple[tuple[str, str], ...], _BeamState] = {}
            for state in beam:
                weights = dict(state.loaded_weight)
                volumes = dict(state.loaded_volume)
                stops = {key: set(value) for key, value in state.stop_containers}
                for container in containers:
                    if not all(_item_fits_container(item, container) for item in group.items):
                        self.states_fit_pruned += 1
                        continue
                    new_weight = weights.get(container.container_id, 0.0) + group.weight_kg
                    new_volume = volumes.get(container.container_id, 0.0) + group.volume_m3
                    if (
                        new_weight > container.max_weight_kg + 1e-9
                        or new_volume > container.volume_m3 + 1e-12
                    ):
                        self.states_capacity_pruned += 1
                        continue
                    assignments = tuple(sorted((
                        *state.assignments,
                        (group.group_id, container.container_id),
                    )))
                    changed_stops = {key: set(value) for key, value in stops.items()}
                    changed_stops.setdefault(group.stop_id, set()).add(container.container_id)
                    candidate = _BeamState(
                        assignments,
                        tuple(sorted({**weights, container.container_id: new_weight}.items())),
                        tuple(sorted({**volumes, container.container_id: new_volume}.items())),
                        tuple(sorted(
                            (key, tuple(sorted(value)))
                            for key, value in changed_stops.items()
                        )),
                    )
                    self.states_generated += 1
                    next_states[assignments] = candidate
            if not next_states:
                self.termination_reason = "no_capacity_feasible_affinity"
                return ()
            beam = _diverse_beam(
                list(next_states.values()), container_map,
                self.utilization_target, self.beam_width,
            )

        complete_states = [
            value for value in beam
            if len(dict(value.loaded_weight)) == len(containers)
        ]
        selected_complete_states = _diverse_complete_states(
            complete_states, container_map, self.utilization_target,
            self.max_plans_per_subset,
        )
        plans = tuple(
            _state_to_plan(value, groups, container_map, self.utilization_target)
            for value in selected_complete_states
        )
        expected_ids = {value.item_id for value in items}
        for plan in plans:
            if set(plan.by_item_id) != expected_ids:
                raise RuntimeError("Affinity planner produced an incomplete plan")
        self.plans_generated += len(plans)
        self.termination_reason = "plans_generated" if plans else "no_plan"
        return plans

    def metadata(self) -> dict[str, object]:
        return {
            "container_assignment_planner": self.planner_id,
            "container_assignment_beam_width": self.beam_width,
            "container_assignment_max_plans_per_subset": self.max_plans_per_subset,
            "container_assignment_utilization_target": self.utilization_target,
            "container_assignment_subsets_evaluated": self.subsets_evaluated,
            "container_assignment_states_generated": self.states_generated,
            "container_assignment_states_capacity_pruned": self.states_capacity_pruned,
            "container_assignment_states_fit_pruned": self.states_fit_pruned,
            "container_assignment_plans_generated": self.plans_generated,
            "container_assignment_deadline_reached": self.deadline_reached,
            "container_assignment_termination_reason": self.termination_reason,
        }


def _assignment_groups(items: list[Item]) -> tuple[_AssignmentGroup, ...]:
    grouped: dict[str, list[Item]] = {}
    for item in items:
        group_id = str(item.source.get("order_id", "")).strip() or item.item_id
        grouped.setdefault(group_id, []).append(item)
    result: list[_AssignmentGroup] = []
    for group_id, values in grouped.items():
        stops = {_stop_id(item) for item in values}
        priorities = {_priority(item) for item in values}
        if len(stops) != 1 or len(priorities) != 1:
            raise ValueError(
                f"Order group {group_id} must declare one delivery stop and priority"
            )
        ordered = tuple(sorted(values, key=lambda item: item.item_id))
        result.append(_AssignmentGroup(
            group_id=group_id,
            item_ids=tuple(item.item_id for item in ordered),
            stop_id=next(iter(stops)),
            priority=next(iter(priorities)),
            weight_kg=sum(item.weight_kg for item in ordered),
            volume_m3=sum(item.volume_m3 for item in ordered),
            items=ordered,
        ))
    return tuple(sorted(
        result,
        key=lambda value: (
            value.priority, -value.volume_m3,
            -max(
                max(item.length_mm, item.width_mm, item.height_mm)
                for item in value.items
            ),
            -value.weight_kg, value.group_id,
        ),
    ))


def _priority(item: Item) -> int:
    try:
        value = int(str(item.source["delivery_priority"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            f"Stop-aware assignment item {item.item_id} requires delivery_priority"
        ) from exc
    if value <= 0:
        raise ValueError("delivery_priority must be positive")
    return value


def _stop_id(item: Item) -> str:
    value = str(item.source.get("delivery_stop_id", "")).strip()
    if not value:
        raise ValueError(
            f"Stop-aware assignment item {item.item_id} requires delivery_stop_id"
        )
    return value


def _item_fits_container(item: Item, container: Container) -> bool:
    return (
        item.length_mm <= container.length_mm + 1e-9
        and item.width_mm <= container.width_mm + 1e-9
        and item.height_mm <= container.height_mm + 1e-9
        and item.weight_kg <= container.max_weight_kg + 1e-9
    )


def _state_score(
    state: _BeamState, containers: Mapping[str, Container], target: float,
) -> tuple[object, ...]:
    weights = dict(state.loaded_weight)
    volumes = dict(state.loaded_volume)
    used = sorted(set(weights) | set(volumes))
    utilizations = [
        max(
            weights.get(value, 0.0) / containers[value].max_weight_kg,
            volumes.get(value, 0.0) / containers[value].volume_m3,
        )
        for value in used
    ]
    fragmentation = sum(
        max(0, len(container_ids) - 1)
        for _, container_ids in state.stop_containers
    )
    overfill = sum(max(0.0, value - target) for value in utilizations)
    imbalance = (
        max(utilizations) - min(utilizations) if len(utilizations) > 1 else 0.0
    )
    return (
        len(used), fragmentation,
        sum(containers[value].cost for value in used),
        overfill, imbalance, state.assignments,
    )


def _state_to_plan(
    state: _BeamState,
    groups: tuple[_AssignmentGroup, ...],
    containers: Mapping[str, Container],
    target: float,
) -> ContainerAffinityPlan:
    score = _state_score(state, containers, target)
    weights = dict(state.loaded_weight)
    volumes = dict(state.loaded_volume)
    preferred = dict(state.assignments)
    used = sorted(set(weights) | set(volumes))
    utilizations = [
        max(
            weights.get(value, 0.0) / containers[value].max_weight_kg,
            volumes.get(value, 0.0) / containers[value].volume_m3,
        )
        for value in used
    ]
    stop_assignments = {key: set(value) for key, value in state.stop_containers}
    affinities = tuple(
        ContainerAffinity(
            group_id=group.group_id,
            stop_id=group.stop_id,
            item_ids=group.item_ids,
            ranked_container_ids=_ranked_containers(
                group, preferred[group.group_id], containers,
                weights, volumes, stop_assignments, target,
            ),
        )
        for group in groups
    )
    return ContainerAffinityPlan(
        container_subset_ids=tuple(sorted(containers)),
        affinities=affinities,
        score=score,
        planned_used_container_count=len(used),
        planned_stop_fragmentation=int(score[1]),
        total_cost=float(score[2]),
        maximum_utilization=max(utilizations, default=0.0),
        utilization_imbalance=(
            max(utilizations) - min(utilizations)
            if len(utilizations) > 1 else 0.0
        ),
    )


def _ranked_containers(
    group: _AssignmentGroup,
    preferred_id: str,
    containers: Mapping[str, Container],
    weights: Mapping[str, float],
    volumes: Mapping[str, float],
    stop_assignments: Mapping[str, set[str]],
    target: float,
) -> tuple[str, ...]:
    def score(container_id: str) -> tuple[object, ...]:
        container = containers[container_id]
        projected_weight = weights.get(container_id, 0.0) + (
            0.0 if container_id == preferred_id else group.weight_kg
        )
        projected_volume = volumes.get(container_id, 0.0) + (
            0.0 if container_id == preferred_id else group.volume_m3
        )
        utilization = max(
            projected_weight / container.max_weight_kg,
            projected_volume / container.volume_m3,
        )
        return (
            0 if container_id == preferred_id else 1,
            0 if container_id in stop_assignments.get(group.stop_id, set()) else 1,
            max(0.0, utilization - target),
            abs(utilization - target),
            container.cost,
            container_id,
        )

    return tuple(sorted(containers, key=score))


def _diverse_beam(
    states: list[_BeamState], containers: Mapping[str, Container],
    target: float, width: int,
) -> list[_BeamState]:
    groups: dict[tuple[int, int], list[_BeamState]] = {}
    for state in states:
        fragmentation = sum(
            max(0, len(container_ids) - 1)
            for _, container_ids in state.stop_containers
        )
        groups.setdefault(
            (len(dict(state.loaded_weight)), fragmentation), []
        ).append(state)
    for values in groups.values():
        values.sort(key=lambda value: _state_score(value, containers, target))
    selected: list[_BeamState] = []
    strata = sorted(groups)
    index = 0
    while len(selected) < width and strata:
        next_strata: list[tuple[int, int]] = []
        for stratum in strata:
            values = groups[stratum]
            if index < len(values):
                selected.append(values[index])
                if len(selected) >= width:
                    break
            if index + 1 < len(values):
                next_strata.append(stratum)
        strata = next_strata
        index += 1
    return sorted(
        selected, key=lambda value: _state_score(value, containers, target)
    )


def _diverse_complete_states(
    states: list[_BeamState], containers: Mapping[str, Container],
    target: float, limit: int,
) -> list[_BeamState]:
    """Keep low-fragmentation plans first without erasing geometric diversity."""
    by_fragmentation: dict[int, list[_BeamState]] = {}
    for state in states:
        fragmentation = sum(
            max(0, len(container_ids) - 1)
            for _, container_ids in state.stop_containers
        )
        by_fragmentation.setdefault(fragmentation, []).append(state)
    for values in by_fragmentation.values():
        values.sort(key=lambda value: _state_score(value, containers, target))
    result: list[_BeamState] = []
    strata = sorted(by_fragmentation)
    index = 0
    while len(result) < limit and strata:
        remaining: list[int] = []
        for fragmentation in strata:
            values = by_fragmentation[fragmentation]
            if index < len(values):
                result.append(values[index])
                if len(result) >= limit:
                    break
            if index + 1 < len(values):
                remaining.append(fragmentation)
        strata = remaining
        index += 1
    return sorted(
        result, key=lambda value: _state_score(value, containers, target)
    )


def _deadline_reached(deadline: float | None) -> bool:
    return deadline is not None and perf_counter() >= deadline
