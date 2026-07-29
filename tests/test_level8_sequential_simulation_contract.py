from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from container_packing.data_loader import load_config
from container_packing.levels.level_08_simulation_contract import (
    SequentialSimulationSettings,
    SimulationEvent,
    SimulationEventType,
)


def _config(root: Path) -> dict:
    return load_config(root / "config/level_08/sequential_simulation_rules.yaml")


def test_level8_sequential_contract_freezes_strict_offline_replay_and_artifacts(root: Path) -> None:
    settings = SequentialSimulationSettings.from_config(_config(root))

    assert settings.execution_mode == "offline_deterministic_replay"
    assert settings.route_source == "declared_delivery_priority"
    assert settings.unloading_policy == "strict_lifo_no_rehandling"
    assert settings.allow_rehandling is False
    assert settings.timing.item_operation_seconds(12.5, operation="load") == 11.25
    assert settings.artifact_paths() == (
        "simulation/simulation_plan.json", "simulation/events.jsonl", "simulation/loading_sequence.csv",
        "simulation/unloading_sequence.csv", "simulation/stop_summary.csv", "simulation/simulation_metrics.json",
        "simulation/simulation_validation.json",
    )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: value["simulation_policy"].update({"allow_rehandling": True}), "allow_rehandling=false"),
        (lambda value: value["timing_model"].update({"seconds_per_kg": -0.1}), "finite non-negative"),
        (lambda value: value["output"].update({"event_log": "../events.jsonl"}), "simple relative name"),
        (lambda value: value["output"].update({"event_log": "simulation_plan.json"}), "must be unique"),
    ],
)
def test_level8_sequential_contract_rejects_ambiguous_or_unsafe_semantics(root: Path, mutate, message: str) -> None:
    config = deepcopy(_config(root))
    mutate(config)

    with pytest.raises(ValueError, match=message):
        SequentialSimulationSettings.from_config(config)


def test_simulation_event_is_serializable_and_rejects_invalid_logical_time() -> None:
    event = SimulationEvent("evt-0001", 0, 0.0, 11.0, SimulationEventType.ITEM_LOADED, "I1", "C1")

    assert event.to_dict()["event_type"] == "item_loaded"
    with pytest.raises(ValueError, match="sequence"):
        SimulationEvent("evt-0002", -1, 0.0, 0.0, SimulationEventType.SIMULATION_STARTED)
    with pytest.raises(ValueError, match="duration_seconds"):
        SimulationEvent("evt-0003", 1, 0.0, -1.0, SimulationEventType.SIMULATION_COMPLETED)
