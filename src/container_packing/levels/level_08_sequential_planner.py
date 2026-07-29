"""Deterministic offline planning for the Level 8 sequential fixture.

The planner is deliberately small and offline. It does not route a vehicle,
model equipment, or mutate a packing solution. It converts a static strict-
LIFO-valid fixture into deterministic loading/unloading orders and logical-time
events, after replaying the independent remaining-state validator.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from ..schemas import Container, Item, Placement, ValidationIssue, ValidationResult
from .level_08_simulation_contract import (
    SequentialSimulationSettings,
    SimulationEvent,
    SimulationEventType,
)
from .level_08_sequential_state_validation import build_level_07_remaining_state_validator
from .level_08_sequential_validation import (
    SequentialUnloadingValidation,
    UnloadingDependency,
    build_unloading_dependency_graph,
    validate_sequential_unloading,
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
) -> SimulationPlan:
    """Create a plan only when initial and sequential strict-LIFO states pass."""
    item_list = list(items)
    container_list = list(containers)
    placement_list = list(placements)
    simulation = SequentialSimulationSettings.from_config(simulation_config)
    unloading = UnloadingSettings.from_config(unloading_config)
    initial_lifo = validate_unloading_lifo(item_list, placement_list, unloading_config)
    if not initial_lifo.result.valid:
        raise ValueError("Cannot build sequential plan: initial static strict-LIFO validation is invalid")

    dependencies = build_unloading_dependency_graph(
        item_list, placement_list, unloading, nesting_relations=nesting_relations,
    )
    attributes = {item.item_id: delivery_attributes_for_item(item) for item in item_list}
    if any(not value.declared_active for value in attributes.values()):
        raise ValueError("Cannot build sequential plan without declared delivery metadata for every item")
    placement_by_id = {value.item_id: value for value in placement_list}
    if set(placement_by_id) != set(attributes):
        raise ValueError("Sequential planner requires exactly one placement per item")

    def unload_key(item_id: str) -> tuple[int, str, str]:
        value = attributes[item_id]
        assert value.delivery_priority is not None
        return (value.delivery_priority, placement_by_id[item_id].container_id, item_id)

    # Reverse every removal precedence for loading. Later stops are preferred
    # first, but a physical supporter/host still loads before its dependent.
    def load_key(item_id: str) -> tuple[int, str, str]:
        value = attributes[item_id]
        assert value.delivery_priority is not None
        return (-value.delivery_priority, placement_by_id[item_id].container_id, item_id)

    unloading_order = _topological_order(tuple(attributes), dependencies, key=unload_key)
    loading_dependencies = tuple(
        UnloadingDependency(edge.successor_item_id, edge.predecessor_item_id, edge.container_id, f"reverse_{edge.reason}")
        for edge in dependencies
    )
    loading_order = _topological_order(tuple(attributes), loading_dependencies, key=load_key)
    state_validator = build_level_07_remaining_state_validator(
        container_list, inherited_config, nesting_relations=nesting_relations,
    )
    validation = validate_sequential_unloading(
        item_list, container_list, placement_list, unloading_config, unloading_order,
        nesting_relations=nesting_relations, state_validator=state_validator,
    )
    if not validation.result.valid:
        raise ValueError("Cannot build sequential plan: independent sequential validation is invalid")
    events = _build_events(loading_order, unloading_order, attributes, placement_by_id, simulation)
    return SimulationPlan(loading_order, unloading_order, dependencies, events, validation)


def _topological_order(
    item_ids: tuple[str, ...], dependencies: Iterable[UnloadingDependency], *, key
) -> tuple[str, ...]:
    predecessors: dict[str, set[str]] = {item_id: set() for item_id in item_ids}
    successors: dict[str, set[str]] = {item_id: set() for item_id in item_ids}
    for edge in dependencies:
        if edge.predecessor_item_id not in predecessors or edge.successor_item_id not in predecessors:
            raise ValueError("Sequential dependency references an unknown item")
        predecessors[edge.successor_item_id].add(edge.predecessor_item_id)
        successors[edge.predecessor_item_id].add(edge.successor_item_id)
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

    def append(event_type: SimulationEventType, duration: float = 0.0, *, item_id: str | None = None, stop_id: str | None = None) -> None:
        nonlocal time_seconds
        event = SimulationEvent(
            f"evt-{len(events) + 1:04d}", len(events), time_seconds, duration, event_type,
            item_id=item_id,
            container_id=placements[item_id].container_id if item_id is not None else None,
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
        append(SimulationEventType.DOOR_OPENED, settings.timing.door_open_seconds, stop_id=stop_id)
        for item_id in item_ids:
            append(
                SimulationEventType.ITEM_UNLOADED,
                settings.timing.item_operation_seconds(placements[item_id].weight_kg, operation="unload"),
                item_id=item_id, stop_id=stop_id,
            )
            append(SimulationEventType.ITEM_DELIVERED, item_id=item_id, stop_id=stop_id)
        append(SimulationEventType.STOP_COMPLETED, stop_id=stop_id)
        append(SimulationEventType.DOOR_CLOSED, settings.timing.door_close_seconds, stop_id=stop_id)
    append(SimulationEventType.SIMULATION_COMPLETED)
    return tuple(events)
