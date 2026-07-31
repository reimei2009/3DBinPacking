"""Deterministic offline planning for the Level 8 sequential fixture.

The planner is deliberately small and offline. It does not route a vehicle,
model equipment, or mutate a packing solution. It converts a static strict-
LIFO-valid fixture into deterministic loading/unloading orders and logical-time
events, after replaying the independent remaining-state validator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Callable, Iterable

from ..schemas import Container, Item, Placement, ValidationIssue, ValidationResult
from .level_08_simulation_contract import (
    SequentialSimulationSettings,
    SimulationEvent,
    SimulationEventType,
)
from .level_08_sequential_state_validation import (
    build_incremental_level_07_remaining_state_validator,
    build_level_07_remaining_state_validator,
)
from .level_08_sequential_validation import (
    SequentialUnloadingValidation,
    UnloadingDependency,
    build_unloading_dependency_graph,
    validate_sequential_unloading,
)
from .level_07_fixture_bundle import balance_rules
from .load_balance import (
    ContainerBalanceAttributes,
    resolve_container_balance_attributes,
)
from .nesting_engine import NestingRelation
from .unloading import UnloadingSettings, delivery_attributes_for_item
from .level_08_validation import validate_unloading_lifo


@dataclass(frozen=True)
class SimulationPlan:
    """Canonical deterministic fixture plan before any event-runtime exists."""

    loading_order: tuple[str, ...]
    unloading_order: tuple[str, ...]
    dependencies: tuple[UnloadingDependency, ...]
    events: tuple[SimulationEvent, ...]
    validation: SequentialUnloadingValidation
    replay_diagnostics: dict[str, Any] = field(default_factory=dict, compare=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "model": "offline_deterministic_dependency_replay_v1",
            "loading_order": list(self.loading_order),
            "unloading_order": list(self.unloading_order),
            "dependencies": [value.to_dict() for value in self.dependencies],
            "sequential_validation": self.validation.payload(),
            "event_count": len(self.events),
        }


class SequentialReplayTimeLimitError(ValueError):
    """A replay deadline is an expected bounded-runtime outcome, not a crash."""

    def __init__(self, diagnostics: dict[str, Any]) -> None:
        super().__init__("Sequential replay exceeded its configured time limit")
        self.diagnostics = diagnostics


class SequentialReplayValidationError(ValueError):
    """A deterministic replay found an invalid state with actionable evidence."""

    def __init__(self, diagnostics: dict[str, Any]) -> None:
        first_code = diagnostics.get("sequential_replay_first_issue_code", "UNKNOWN")
        first_item = diagnostics.get("sequential_replay_first_failed_item_id")
        suffix = f" at item {first_item}" if first_item else ""
        super().__init__(f"Sequential replay state validation failed: {first_code}{suffix}")
        self.diagnostics = diagnostics


@dataclass
class _ContainerMoment:
    """Mutable x/y mass moments used only while constructing an unload order."""

    weight_kg: float = 0.0
    x_moment: float = 0.0
    y_moment: float = 0.0

    def offsets(
        self,
        *,
        container: Container,
        attributes: ContainerBalanceAttributes,
    ) -> tuple[float, float]:
        if self.weight_kg <= 1e-12:
            return 0.0, 0.0
        longitudinal = self.x_moment / self.weight_kg / container.length_mm
        lateral = self.y_moment / self.weight_kg / container.width_mm
        return (
            abs(longitudinal - attributes.target_longitudinal_ratio),
            abs(lateral - attributes.target_lateral_ratio),
        )

    def projected_offsets(
        self,
        *,
        removed_weight_kg: float,
        removed_center_x_mm: float,
        removed_center_y_mm: float,
        container: Container,
        attributes: ContainerBalanceAttributes,
    ) -> tuple[bool, float, float]:
        remaining_weight = self.weight_kg - removed_weight_kg
        if remaining_weight <= 1e-12:
            return True, 0.0, 0.0
        longitudinal = (
            (self.x_moment - removed_weight_kg * removed_center_x_mm)
            / remaining_weight
            / container.length_mm
        )
        lateral = (
            (self.y_moment - removed_weight_kg * removed_center_y_mm)
            / remaining_weight
            / container.width_mm
        )
        longitudinal_offset = abs(
            longitudinal - attributes.target_longitudinal_ratio
        )
        lateral_offset = abs(lateral - attributes.target_lateral_ratio)
        safe = (
            longitudinal_offset
            <= attributes.max_longitudinal_offset_ratio + 1e-9
            and lateral_offset <= attributes.max_lateral_offset_ratio + 1e-9
        )
        return safe, longitudinal_offset, lateral_offset

    def remove(
        self, weight_kg: float, center_x_mm: float, center_y_mm: float
    ) -> None:
        self.weight_kg -= weight_kg
        self.x_moment -= weight_kg * center_x_mm
        self.y_moment -= weight_kg * center_y_mm

    def add(
        self, weight_kg: float, center_x_mm: float, center_y_mm: float
    ) -> None:
        self.weight_kg += weight_kg
        self.x_moment += weight_kg * center_x_mm
        self.y_moment += weight_kg * center_y_mm


def validate_deterministic_plan(plan: SimulationPlan) -> ValidationResult:
    """Independently validate the fixture plan's logical event timeline."""
    issues: list[ValidationIssue] = []
    if not plan.validation.result.valid:
        issues.append(ValidationIssue("SEQUENTIAL_PLAN_REPLAY_INVALID", "Sequential removal replay is invalid"))
    events = list(plan.events)
    if [event.sequence for event in events] != list(range(len(events))):
        issues.append(ValidationIssue("SEQUENTIAL_EVENT_SEQUENCE_INVALID", "Event sequence must be contiguous from zero"))
    if any(event.simulation_time_seconds > next_event.simulation_time_seconds for event, next_event in zip(events, events[1:])):
        issues.append(ValidationIssue("SEQUENTIAL_EVENT_TIME_INVALID", "Logical event times must be non-decreasing"))
    if tuple(event.item_id for event in events if event.event_type is SimulationEventType.ITEM_LOADED) != plan.loading_order:
        issues.append(ValidationIssue("SEQUENTIAL_LOADING_ORDER_INVALID", "item_loaded events differ from the loading order"))
    if tuple(event.item_id for event in events if event.event_type is SimulationEventType.ITEM_UNLOADED) != plan.unloading_order:
        issues.append(ValidationIssue("SEQUENTIAL_UNLOADING_ORDER_INVALID", "item_unloaded events differ from the unloading order"))
    if tuple(event.item_id for event in events if event.event_type is SimulationEventType.ITEM_DELIVERED) != plan.unloading_order:
        issues.append(ValidationIssue("SEQUENTIAL_DELIVERY_ORDER_INVALID", "item_delivered events differ from the unloading order"))
    expected_boundaries = (SimulationEventType.SIMULATION_STARTED, SimulationEventType.SIMULATION_COMPLETED)
    if not events or (events[0].event_type, events[-1].event_type) != expected_boundaries:
        issues.append(ValidationIssue("SEQUENTIAL_EVENT_BOUNDARY_INVALID", "Plan must start and end with simulation boundary events"))
    opened: set[tuple[str, str]] = set()
    closed: set[tuple[str, str]] = set()
    for event in events:
        if event.event_type in {SimulationEventType.DOOR_OPENED, SimulationEventType.DOOR_CLOSED}:
            if not event.delivery_stop_id or not event.container_id:
                issues.append(ValidationIssue(
                    "SEQUENTIAL_DOOR_EVENT_SCOPE_INVALID",
                    "Door events must identify both delivery stop and container",
                ))
                continue
            key = (event.delivery_stop_id, event.container_id)
            target = opened if event.event_type is SimulationEventType.DOOR_OPENED else closed
            if key in target:
                issues.append(ValidationIssue(
                    "SEQUENTIAL_DOOR_EVENT_DUPLICATE",
                    f"Duplicate {event.event_type.value} event for stop/container {key}",
                ))
            target.add(key)
    if opened != closed:
        issues.append(ValidationIssue(
            "SEQUENTIAL_DOOR_EVENT_PAIR_INVALID",
            "Every stop/container door-open event must have exactly one matching close event",
        ))
    return ValidationResult(not issues, issues)


def simulation_metrics(plan: SimulationPlan) -> dict[str, Any]:
    """Stable metrics from logical event durations, not wall-clock execution."""
    loading = sum(event.duration_seconds for event in plan.events if event.event_type is SimulationEventType.ITEM_LOADED)
    unloading = sum(event.duration_seconds for event in plan.events if event.event_type is SimulationEventType.ITEM_UNLOADED)
    door = sum(event.duration_seconds for event in plan.events if event.event_type in {SimulationEventType.DOOR_OPENED, SimulationEventType.DOOR_CLOSED})
    total = max((event.simulation_time_seconds + event.duration_seconds for event in plan.events), default=0.0)
    stops = sorted({event.delivery_stop_id for event in plan.events if event.event_type is SimulationEventType.STOP_COMPLETED and event.delivery_stop_id})
    return {
        "schema_version": "1.0",
        "model": "offline_deterministic_dependency_replay_v1",
        "logical_total_seconds": total,
        "logical_loading_seconds": loading,
        "logical_unloading_seconds": unloading,
        "logical_door_seconds": door,
        "event_count": len(plan.events),
        "loading_item_count": len(plan.loading_order),
        "unloading_item_count": len(plan.unloading_order),
        "stop_count": len(stops),
        "stop_ids": stops,
    }


def stop_summary_rows(plan: SimulationPlan) -> list[dict[str, Any]]:
    """Summarize deterministic unload events per declared stop."""
    rows: list[dict[str, Any]] = []
    by_stop: dict[str, list[SimulationEvent]] = {}
    for event in plan.events:
        if event.event_type is SimulationEventType.ITEM_UNLOADED and event.delivery_stop_id:
            by_stop.setdefault(event.delivery_stop_id, []).append(event)
    for stop_id, events in sorted(by_stop.items(), key=lambda value: (value[1][0].simulation_time_seconds, value[0])):
        rows.append({
            "delivery_stop_id": stop_id,
            "unloaded_item_count": len(events),
            "first_unload_time_seconds": events[0].simulation_time_seconds,
            "last_unload_end_seconds": events[-1].simulation_time_seconds + events[-1].duration_seconds,
            "container_ids": ",".join(sorted({event.container_id for event in events if event.container_id})),
            "item_ids": ",".join(event.item_id for event in events if event.item_id),
        })
    return rows


def build_deterministic_fixture_plan(
    items: Iterable[Item],
    containers: Iterable[Container],
    placements: Iterable[Placement],
    *,
    unloading_config: dict[str, Any],
    simulation_config: dict[str, Any],
    inherited_config: dict[str, Any],
    nesting_relations: Iterable[NestingRelation] = (),
    replay_time_limit_seconds: float = 45.0,
    clock: Callable[[], float] = monotonic,
    state_validation_mode: str = "incremental_container_local_v1",
) -> SimulationPlan:
    """Create a plan only when initial and sequential strict-LIFO states pass."""
    started = clock()
    deadline = started + max(0.0, float(replay_time_limit_seconds))
    item_list = list(items)
    container_list = list(containers)
    placement_list = list(placements)
    fixed_relations = tuple(nesting_relations)
    simulation = SequentialSimulationSettings.from_config(simulation_config)
    unloading = UnloadingSettings.from_config(unloading_config)
    initial_lifo = validate_unloading_lifo(item_list, placement_list, unloading_config)
    if not initial_lifo.result.valid:
        raise ValueError("Cannot build sequential plan: initial static strict-LIFO validation is invalid")

    dependencies = build_unloading_dependency_graph(
        item_list, placement_list, unloading, nesting_relations=fixed_relations,
    )
    graph_seconds = clock() - started
    if clock() >= deadline:
        raise SequentialReplayTimeLimitError({
            "sequential_replay_termination_reason": "deadline_during_dependency_graph",
            "sequential_replay_graph_runtime_seconds": graph_seconds,
            "sequential_replay_state_runtime_seconds": 0.0,
            "sequential_replay_time_limit_seconds": replay_time_limit_seconds,
            "sequential_replay_states_checked": 0,
        })
    attributes = {item.item_id: delivery_attributes_for_item(item) for item in item_list}
    if any(not value.declared_active for value in attributes.values()):
        raise ValueError("Cannot build sequential plan without declared delivery metadata for every item")
    placement_by_id = {value.item_id: value for value in placement_list}
    if set(placement_by_id) != set(attributes):
        raise ValueError("Sequential planner requires exactly one placement per item")

    # Reverse every removal precedence for loading. Later stops are preferred
    # first, but a physical supporter/host still loads before its dependent.
    def load_key(item_id: str) -> tuple[int, str, str]:
        value = attributes[item_id]
        assert value.delivery_priority is not None
        return (-value.delivery_priority, placement_by_id[item_id].container_id, item_id)

    unloading_order, unloading_order_diagnostics = _balance_aware_unloading_order(
        tuple(attributes),
        dependencies,
        attributes=attributes,
        items=item_list,
        containers=container_list,
        placements=placement_list,
        nesting_relations=fixed_relations,
        balance_config=balance_rules(inherited_config),
        deadline=deadline,
        clock=clock,
    )
    loading_dependencies = tuple(
        UnloadingDependency(edge.successor_item_id, edge.predecessor_item_id, edge.container_id, f"reverse_{edge.reason}")
        for edge in dependencies
    )
    loading_order = _topological_order(tuple(attributes), loading_dependencies, key=load_key)
    if state_validation_mode == "incremental_container_local_v1":
        state_validator = build_incremental_level_07_remaining_state_validator(
            item_list, container_list, placement_list, inherited_config,
            nesting_relations=fixed_relations,
        )
        if not state_validator.initial_result.valid:
            raise ValueError("Cannot build sequential plan: initial Level 1--7 validation is invalid")
    elif state_validation_mode == "full_state_v1":
        state_validator = build_level_07_remaining_state_validator(
            container_list, inherited_config, nesting_relations=fixed_relations,
        )
    else:
        raise ValueError(f"Unknown sequential state_validation_mode: {state_validation_mode}")
    state_started = clock()
    validation = validate_sequential_unloading(
        item_list, container_list, placement_list, unloading_config, unloading_order,
        nesting_relations=fixed_relations, state_validator=state_validator,
        state_validation_mode=state_validation_mode, deadline_monotonic=deadline, clock=clock,
    )
    state_seconds = clock() - state_started
    diagnostics = {
        "sequential_replay_time_limit_seconds": replay_time_limit_seconds,
        "sequential_replay_graph_runtime_seconds": graph_seconds,
        "sequential_replay_state_runtime_seconds": state_seconds,
        "sequential_replay_total_runtime_seconds": clock() - started,
        "sequential_replay_states_checked": validation.checked_state_count,
        "sequential_replay_termination_reason": validation.termination_reason,
        "sequential_state_validation_mode": state_validation_mode,
        **unloading_order_diagnostics,
    }
    if state_validation_mode == "incremental_container_local_v1":
        diagnostics.update(state_validator.diagnostics())
    if validation.termination_reason == "replay_time_limit":
        raise SequentialReplayTimeLimitError(diagnostics)
    if not validation.result.valid:
        diagnostics.update(_validation_failure_diagnostics(validation))
        raise SequentialReplayValidationError(diagnostics)
    event_started = clock()
    events = _build_events(loading_order, unloading_order, attributes, placement_by_id, simulation)
    # Event construction is the deterministic work immediately preceding the
    # isolated artifact writer; actual filesystem I/O remains outside the
    # replay validator and is deliberately not part of its deadline.
    diagnostics["sequential_replay_event_writing_seconds"] = clock() - event_started
    diagnostics["sequential_replay_total_runtime_seconds"] = clock() - started
    return SimulationPlan(loading_order, unloading_order, dependencies, events, validation, diagnostics)


def _balance_aware_unloading_order(
    item_ids: tuple[str, ...],
    dependencies: Iterable[UnloadingDependency],
    *,
    attributes: dict[str, Any],
    items: list[Item],
    containers: list[Container],
    placements: list[Placement],
    nesting_relations: tuple[NestingRelation, ...],
    balance_config: dict[str, Any],
    deadline: float,
    clock: Callable[[], float],
) -> tuple[tuple[str, ...], dict[str, Any]]:
    """Choose a balance-safe ready item without weakening route precedence.

    Delivery priority is a hard outer order. Support and nesting edges define
    the ready set within that priority. Among those ready items, the candidate
    whose removal leaves the affected container closest to its Level 7 COG
    target is selected. Empty containers are valid terminal states.

    Nested members contribute mass at their compound root's external x/y
    center, matching the Level 7 compound-root COG model. The dependency graph
    guarantees that a child is removed before its host.
    """
    predecessors, _ = _dependency_maps(item_ids, dependencies)
    placement_by_id = {placement.item_id: placement for placement in placements}
    container_by_id = {container.container_id: container for container in containers}
    balance_attributes = resolve_container_balance_attributes(
        containers, balance_config
    )
    root_by_item = _nesting_root_by_item(item_ids, nesting_relations)
    contribution: dict[str, tuple[str, float, float, float]] = {}
    moments: dict[str, _ContainerMoment] = {}
    for item_id in item_ids:
        root_id = root_by_item[item_id]
        root_placement = placement_by_id[root_id]
        item_placement = placement_by_id[item_id]
        center_x = root_placement.x_mm + root_placement.length_mm / 2.0
        center_y = root_placement.y_mm + root_placement.width_mm / 2.0
        value = (
            root_placement.container_id,
            item_placement.weight_kg,
            center_x,
            center_y,
        )
        contribution[item_id] = value
        moment = moments.setdefault(root_placement.container_id, _ContainerMoment())
        moment.weight_kg += value[1]
        moment.x_moment += value[1] * value[2]
        moment.y_moment += value[1] * value[3]

    remaining = set(item_ids)
    removed: set[str] = set()
    order: list[str] = []
    candidates_evaluated = 0
    backtracks = 0
    failed_states = 0
    while remaining:
        if clock() >= deadline:
            raise SequentialReplayTimeLimitError({
                "sequential_replay_termination_reason": "deadline_during_balance_aware_unloading_order",
                "sequential_replay_time_limit_seconds": max(0.0, deadline - clock()),
                "sequential_replay_states_checked": 0,
                "sequential_balance_order_candidates_evaluated": candidates_evaluated,
            })
        current_priority = min(
            int(attributes[item_id].delivery_priority) for item_id in remaining
        )
        priority_items = {
            item_id
            for item_id in remaining
            if int(attributes[item_id].delivery_priority) == current_priority
        }
        impossible_dependencies = sorted(
            item_id
            for item_id in priority_items
            if any(
                predecessor in remaining
                and predecessor not in priority_items
                for predecessor in predecessors[item_id]
            )
        )
        if impossible_dependencies:
            raise SequentialReplayValidationError({
                "sequential_replay_termination_reason": "delivery_priority_dependency_conflict",
                "sequential_replay_first_failed_sequence": len(order),
                "sequential_replay_first_failed_item_id": impossible_dependencies[0],
                "sequential_replay_first_issue_code": "DELIVERY_PRIORITY_DEPENDENCY_CONFLICT",
                "sequential_replay_first_issue_message": (
                    f"Delivery priority {current_priority} has no dependency-ready item; "
                    "a later stop cannot be processed first"
                ),
                "sequential_balance_order_priority": current_priority,
                "sequential_balance_order_ready_item_ids": [],
                "sequential_balance_order_blocked_item_ids": impossible_dependencies,
                "sequential_balance_order_candidates_evaluated": candidates_evaluated,
            })

        failed: set[frozenset[str]] = set()
        deepest_failure: dict[str, Any] = {
            "depth": -1,
            "ready": [],
            "projected": [],
        }

        def search_stop(
            stop_remaining: frozenset[str],
        ) -> tuple[str, ...] | None:
            nonlocal candidates_evaluated, backtracks, failed_states
            if not stop_remaining:
                return ()
            if clock() >= deadline:
                raise SequentialReplayTimeLimitError({
                    "sequential_replay_termination_reason": (
                        "deadline_during_balance_aware_unloading_order"
                    ),
                    "sequential_replay_states_checked": 0,
                    "sequential_balance_order_candidates_evaluated": (
                        candidates_evaluated
                    ),
                    "sequential_balance_order_backtracks": backtracks,
                })
            if stop_remaining in failed:
                return None
            removed_in_stop = priority_items - set(stop_remaining)
            available_removed = removed | removed_in_stop
            ready = sorted(
                (
                    item_id
                    for item_id in stop_remaining
                    if predecessors[item_id] <= available_removed
                ),
                key=lambda item_id: (
                    placement_by_id[item_id].container_id,
                    item_id,
                ),
            )
            current_offsets = {
                container_id: moment.offsets(
                    container=container_by_id[container_id],
                    attributes=balance_attributes[container_id],
                )
                for container_id, moment in moments.items()
            }
            ranked: list[
                tuple[tuple[float, float, str, str], str, float, float]
            ] = []
            projected: list[tuple[float, float, str]] = []
            for item_id in ready:
                container_id, weight, center_x, center_y = contribution[item_id]
                safe, longitudinal_offset, lateral_offset = moments[
                    container_id
                ].projected_offsets(
                    removed_weight_kg=weight,
                    removed_center_x_mm=center_x,
                    removed_center_y_mm=center_y,
                    container=container_by_id[container_id],
                    attributes=balance_attributes[container_id],
                )
                candidates_evaluated += 1
                projected.append((longitudinal_offset, lateral_offset, item_id))
                if safe:
                    next_offsets = {
                        **current_offsets,
                        container_id: (longitudinal_offset, lateral_offset),
                    }
                    ranked.append((
                        (
                            max(max(offsets) for offsets in next_offsets.values()),
                            sum(sum(offsets) for offsets in next_offsets.values()),
                            container_id,
                            item_id,
                        ),
                        item_id,
                        longitudinal_offset,
                        lateral_offset,
                    ))
            depth = len(priority_items) - len(stop_remaining)
            if not ranked and depth > int(deepest_failure["depth"]):
                deepest_failure.update({
                    "depth": depth,
                    "ready": ready,
                    "projected": projected,
                })
            for _, selected, _, _ in sorted(ranked, key=lambda value: value[0]):
                container_id, weight, center_x, center_y = contribution[selected]
                moments[container_id].remove(weight, center_x, center_y)
                suffix = search_stop(stop_remaining - {selected})
                if suffix is not None:
                    return (selected, *suffix)
                moments[container_id].add(weight, center_x, center_y)
                backtracks += 1
            failed.add(stop_remaining)
            failed_states += 1
            return None

        stop_order = search_stop(frozenset(priority_items))
        if stop_order is None:
            projected = list(deepest_failure["projected"])
            ready = list(deepest_failure["ready"])
            best = (
                min(
                    projected,
                    key=lambda value: (
                        max(value[0], value[1]),
                        value[0] + value[1],
                        value[2],
                    ),
                )
                if projected
                else (float("inf"), float("inf"), ready[0] if ready else None)
            )
            raise SequentialReplayValidationError({
                "sequential_replay_termination_reason": "no_balance_safe_removal",
                "sequential_replay_first_failed_sequence": (
                    len(order) + int(deepest_failure["depth"])
                ),
                "sequential_replay_first_failed_item_id": best[2],
                "sequential_replay_first_issue_code": "NO_BALANCE_SAFE_REMOVAL",
                "sequential_replay_first_issue_message": (
                    f"No complete balance-safe removal order exists within "
                    f"delivery priority {current_priority} under the configured "
                    "Level 7 COG band and dependency graph"
                ),
                "sequential_balance_order_priority": current_priority,
                "sequential_balance_order_ready_item_ids": ready,
                "sequential_balance_order_best_candidate_item_id": best[2],
                "sequential_balance_order_best_longitudinal_offset_ratio": best[0],
                "sequential_balance_order_best_lateral_offset_ratio": best[1],
                "sequential_balance_order_candidates_evaluated": candidates_evaluated,
                "sequential_balance_order_backtracks": backtracks,
                "sequential_balance_order_failed_states": failed_states,
            })

        # The recursive search restores moments only on failed branches; its
        # successful branch is already committed in this exact order.
        order.extend(stop_order)
        removed.update(stop_order)
        remaining.difference_update(stop_order)

    return tuple(order), {
        "sequential_unloading_order_mode": (
            "delivery_priority_dependency_balance_aware_backtracking_v2"
        ),
        "sequential_balance_order_candidates_evaluated": candidates_evaluated,
        "sequential_balance_order_hard_cog_gate": True,
        "sequential_balance_order_backtracks": backtracks,
        "sequential_balance_order_failed_states": failed_states,
    }


def _dependency_maps(
    item_ids: tuple[str, ...],
    dependencies: Iterable[UnloadingDependency],
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    predecessors: dict[str, set[str]] = {item_id: set() for item_id in item_ids}
    successors: dict[str, set[str]] = {item_id: set() for item_id in item_ids}
    for edge in dependencies:
        if (
            edge.predecessor_item_id not in predecessors
            or edge.successor_item_id not in predecessors
        ):
            raise ValueError("Sequential dependency references an unknown item")
        predecessors[edge.successor_item_id].add(edge.predecessor_item_id)
        successors[edge.predecessor_item_id].add(edge.successor_item_id)
    return predecessors, successors


def _nesting_root_by_item(
    item_ids: tuple[str, ...], relations: tuple[NestingRelation, ...]
) -> dict[str, str]:
    parent_by_child: dict[str, str] = {}
    for relation in relations:
        if relation.child_item_id in parent_by_child:
            raise ValueError(
                f"Nested item {relation.child_item_id} has more than one host"
            )
        parent_by_child[relation.child_item_id] = relation.host_item_id
    roots: dict[str, str] = {}
    for item_id in item_ids:
        current = item_id
        visited: set[str] = set()
        while current in parent_by_child:
            if current in visited:
                raise ValueError("Sequential nesting relation graph contains a cycle")
            visited.add(current)
            current = parent_by_child[current]
        if current not in item_ids:
            raise ValueError(
                f"Sequential nesting relation references unknown host {current}"
            )
        roots[item_id] = current
    return roots


def _validation_failure_diagnostics(
    validation: SequentialUnloadingValidation,
) -> dict[str, Any]:
    """Expose the first failed state without serializing a partial plan."""
    first_step = next((step for step in validation.steps if step.issues), None)
    first_issue = (
        first_step.issues[0]
        if first_step is not None and first_step.issues
        else (validation.result.issues[0] if validation.result.issues else None)
    )
    return {
        "sequential_replay_validation_issue_count": len(validation.result.issues),
        "sequential_replay_validation_issue_codes": [
            issue.code for issue in validation.result.issues[:10]
        ],
        "sequential_replay_first_failed_sequence": (
            first_step.sequence if first_step is not None else None
        ),
        "sequential_replay_first_failed_item_id": (
            first_step.item_id if first_step is not None else None
        ),
        "sequential_replay_first_issue_code": (
            first_issue.code if first_issue is not None else None
        ),
        "sequential_replay_first_issue_message": (
            first_issue.message if first_issue is not None else None
        ),
    }


def _topological_order(
    item_ids: tuple[str, ...], dependencies: Iterable[UnloadingDependency], *, key
) -> tuple[str, ...]:
    predecessors, successors = _dependency_maps(item_ids, dependencies)
    available = sorted((item_id for item_id, values in predecessors.items() if not values), key=key)
    result: list[str] = []
    while available:
        item_id = available.pop(0)
        result.append(item_id)
        for successor in sorted(successors[item_id], key=key):
            predecessors[successor].remove(item_id)
            if not predecessors[successor]:
                available.append(successor)
        available.sort(key=key)
    if len(result) != len(item_ids):
        remaining = sorted(item_id for item_id, values in predecessors.items() if values)
        raise ValueError("Sequential dependency graph contains a cycle: " + ", ".join(remaining))
    return tuple(result)


def _build_events(
    loading_order: tuple[str, ...],
    unloading_order: tuple[str, ...],
    attributes: dict[str, Any],
    placements: dict[str, Placement],
    settings: SequentialSimulationSettings,
) -> tuple[SimulationEvent, ...]:
    events: list[SimulationEvent] = []
    time_seconds = 0.0

    def append(
        event_type: SimulationEventType,
        duration: float = 0.0,
        *,
        item_id: str | None = None,
        stop_id: str | None = None,
        container_id: str | None = None,
    ) -> None:
        nonlocal time_seconds
        event = SimulationEvent(
            f"evt-{len(events) + 1:04d}", len(events), time_seconds, duration, event_type,
            item_id=item_id,
            container_id=placements[item_id].container_id if item_id is not None else container_id,
            delivery_stop_id=stop_id,
        )
        events.append(event)
        time_seconds += duration

    append(SimulationEventType.SIMULATION_STARTED)
    append(SimulationEventType.LOADING_STARTED)
    for item_id in loading_order:
        append(
            SimulationEventType.ITEM_LOADED,
            settings.timing.item_operation_seconds(placements[item_id].weight_kg, operation="load"),
            item_id=item_id,
        )
    append(SimulationEventType.LOADING_COMPLETED)

    by_stop: dict[tuple[int, str], list[str]] = {}
    for item_id in unloading_order:
        attribute = attributes[item_id]
        assert attribute.delivery_priority is not None and attribute.delivery_stop_id is not None
        by_stop.setdefault((attribute.delivery_priority, attribute.delivery_stop_id), []).append(item_id)
    for (_priority, stop_id), item_ids in sorted(by_stop.items()):
        by_container: dict[str, list[str]] = {}
        for item_id in item_ids:
            by_container.setdefault(placements[item_id].container_id, []).append(item_id)
        for container_id, container_items in sorted(by_container.items()):
            append(
                SimulationEventType.DOOR_OPENED,
                settings.timing.door_open_seconds,
                stop_id=stop_id,
                container_id=container_id,
            )
            for item_id in container_items:
                append(
                    SimulationEventType.ITEM_UNLOADED,
                    settings.timing.item_operation_seconds(placements[item_id].weight_kg, operation="unload"),
                    item_id=item_id, stop_id=stop_id,
                )
                append(SimulationEventType.ITEM_DELIVERED, item_id=item_id, stop_id=stop_id)
            append(
                SimulationEventType.DOOR_CLOSED,
                settings.timing.door_close_seconds,
                stop_id=stop_id,
                container_id=container_id,
            )
        append(SimulationEventType.STOP_COMPLETED, stop_id=stop_id)
    append(SimulationEventType.SIMULATION_COMPLETED)
    return tuple(events)
