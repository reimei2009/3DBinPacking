"""Pure schema contract for a future deterministic Level 8 replay.

The existing Level 8 validator assesses a *static* final packing.  This module
does not simulate removal yet.  It freezes the vocabulary, deterministic time
model, and isolated output names that a later replay engine must use, so route
or event code cannot silently redefine strict-LIFO semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from pathlib import PurePosixPath
from typing import Any


class SimulationItemState(StrEnum):
    """Only states allowed by the first offline replay contract."""

    PENDING_LOAD = "pending_load"
    IN_CONTAINER = "in_container"
    DELIVERED = "delivered"


class SimulationEventType(StrEnum):
    """Versioned event vocabulary; no event executor is implemented yet."""

    SIMULATION_STARTED = "simulation_started"
    LOADING_STARTED = "loading_started"
    ITEM_LOADED = "item_loaded"
    LOADING_COMPLETED = "loading_completed"
    DOOR_OPENED = "door_opened"
    ITEM_UNLOADED = "item_unloaded"
    ITEM_DELIVERED = "item_delivered"
    STOP_COMPLETED = "stop_completed"
    DOOR_CLOSED = "door_closed"
    SIMULATION_COMPLETED = "simulation_completed"
    SIMULATION_FAILED = "simulation_failed"


@dataclass(frozen=True)
class SimulationTiming:
    model_id: str
    loading_base_seconds: float
    unloading_base_seconds: float
    seconds_per_kg: float
    door_open_seconds: float
    door_close_seconds: float
    travel_seconds_between_declared_stops: float

    def item_operation_seconds(self, weight_kg: float, *, operation: str) -> float:
        """Return a deterministic declared-duration formula for a future engine."""
        _non_negative_finite(weight_kg, "weight_kg")
        if operation == "load":
            base = self.loading_base_seconds
        elif operation == "unload":
            base = self.unloading_base_seconds
        else:
            raise ValueError("Simulation operation must be 'load' or 'unload'")
        return base + self.seconds_per_kg * weight_kg


@dataclass(frozen=True)
class SequentialSimulationSettings:
    """Validated, runtime-neutral Level 8 sequential simulation contract."""

    execution_mode: str
    route_source: str
    priority_direction: str
    unloading_policy: str
    allow_rehandling: bool
    state_model: str
    timing: SimulationTiming
    output_directory: str
    plan_document: str
    event_log: str
    loading_sequence_table: str
    unloading_sequence_table: str
    stop_summary_table: str
    metrics_document: str
    validation_document: str

    @classmethod
    def from_config(cls, config: dict[str, Any]) -> "SequentialSimulationSettings":
        if config.get("contract_version") != 1:
            raise ValueError("Level 8 sequential simulation contract_version must be 1")
        if config.get("level_id") != "level_08":
            raise ValueError("Level 8 sequential simulation contract requires level_id='level_08'")
        if config.get("status") != "data_contract_only":
            raise ValueError("Level 8 sequential simulation contract must remain data_contract_only")
        policy = _mapping(config, "simulation_policy")
        execution_mode = _exact_text(policy, "execution_mode", "offline_deterministic_replay")
        route_source = _exact_text(policy, "route_source", "declared_delivery_priority")
        priority_direction = _exact_text(policy, "priority_direction", "ascending_is_earlier_delivery")
        unloading_policy = _exact_text(policy, "unloading_policy", "strict_lifo_no_rehandling")
        allow_rehandling = policy.get("allow_rehandling")
        if allow_rehandling is not False:
            raise ValueError("Strict Level 8 sequential simulation requires allow_rehandling=false")
        state_model = _exact_text(policy, "state_model", "item_pending_load_in_container_delivered_v1")

        timing_data = _mapping(config, "timing_model")
        timing = SimulationTiming(
            _exact_text(timing_data, "model_id", "deterministic_item_mass_linear_v1"),
            _number(timing_data, "loading_base_seconds"),
            _number(timing_data, "unloading_base_seconds"),
            _number(timing_data, "seconds_per_kg"),
            _number(timing_data, "door_open_seconds"),
            _number(timing_data, "door_close_seconds"),
            _number(timing_data, "travel_seconds_between_declared_stops"),
        )

        output = _mapping(config, "output")
        names = {
            key: _safe_relative_name(output, key)
            for key in (
                "directory", "plan_document", "event_log", "loading_sequence_table",
                "unloading_sequence_table", "stop_summary_table", "metrics_document", "validation_document",
            )
        }
        artifact_names = tuple(value for key, value in names.items() if key != "directory")
        if len(set(artifact_names)) != len(artifact_names):
            raise ValueError("Level 8 sequential simulation output artifact names must be unique")
        return cls(timing=timing, **{
            "execution_mode": execution_mode,
            "route_source": route_source,
            "priority_direction": priority_direction,
            "unloading_policy": unloading_policy,
            "allow_rehandling": allow_rehandling,
            "state_model": state_model,
            "output_directory": names["directory"],
            "plan_document": names["plan_document"],
            "event_log": names["event_log"],
            "loading_sequence_table": names["loading_sequence_table"],
            "unloading_sequence_table": names["unloading_sequence_table"],
            "stop_summary_table": names["stop_summary_table"],
            "metrics_document": names["metrics_document"],
            "validation_document": names["validation_document"],
        })

    def artifact_paths(self) -> tuple[str, ...]:
        """Paths relative to one isolated run directory, in deterministic order."""
        return tuple(
            f"{self.output_directory}/{name}"
            for name in (
                self.plan_document, self.event_log, self.loading_sequence_table,
                self.unloading_sequence_table, self.stop_summary_table,
                self.metrics_document, self.validation_document,
            )
        )


@dataclass(frozen=True)
class SimulationEvent:
    """A serializable future event with deterministic logical time only."""

    event_id: str
    sequence: int
    simulation_time_seconds: float
    duration_seconds: float
    event_type: SimulationEventType
    item_id: str | None = None
    container_id: str | None = None
    delivery_stop_id: str | None = None

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise ValueError("Simulation event_id must be non-empty")
        if self.sequence < 0:
            raise ValueError("Simulation event sequence must be non-negative")
        _non_negative_finite(self.simulation_time_seconds, "simulation_time_seconds")
        _non_negative_finite(self.duration_seconds, "duration_seconds")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "event_id": self.event_id,
            "sequence": self.sequence,
            "simulation_time_seconds": self.simulation_time_seconds,
            "duration_seconds": self.duration_seconds,
            "event_type": self.event_type.value,
            "item_id": self.item_id,
            "container_id": self.container_id,
            "delivery_stop_id": self.delivery_stop_id,
        }


def _mapping(config: dict[str, Any], key: str) -> dict[str, Any]:
    value = config.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Level 8 sequential simulation contract requires mapping '{key}'")
    return value


def _exact_text(config: dict[str, Any], key: str, expected: str) -> str:
    value = config.get(key)
    if value != expected:
        raise ValueError(f"Level 8 sequential simulation '{key}' must be '{expected}'")
    return expected


def _number(config: dict[str, Any], key: str) -> float:
    try:
        value = float(config.get(key))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Level 8 sequential simulation '{key}' must be a finite non-negative number") from exc
    _non_negative_finite(value, key)
    return value


def _non_negative_finite(value: float, label: str) -> None:
    if not isfinite(value) or value < 0:
        raise ValueError(f"Level 8 sequential simulation '{label}' must be a finite non-negative number")


def _safe_relative_name(config: dict[str, Any], key: str) -> str:
    value = config.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Level 8 sequential simulation output '{key}' must be a non-empty relative name")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or len(path.parts) != 1:
        raise ValueError(f"Level 8 sequential simulation output '{key}' must be a simple relative name")
    return path.name
