from __future__ import annotations

from pathlib import Path

import yaml
import pytest

from container_packing.data_loader import load_config
from container_packing.levels.level_08_sequential_validation import (
    build_unloading_dependency_graph,
    validate_sequential_unloading,
)
from container_packing.levels.level_08_sequential_state_validation import (
    build_level_07_remaining_state_validator,
    filter_remaining_nesting_relations,
)
from container_packing.levels.level_08_sequential_planner import build_deterministic_fixture_plan
from container_packing.levels.level_08_sequential_output import (
    validate_sequential_fixture_artifacts,
    write_sequential_fixture_artifacts,
)
from container_packing.levels.level_08_simulation_contract import SequentialSimulationSettings
from container_packing.levels.nesting_engine import NestingRelation
from container_packing.levels.unloading import UnloadingSettings
from container_packing.schemas import Container, Item, Placement, ValidationResult


def _settings(root: Path) -> tuple[dict, UnloadingSettings]:
    config = load_config(root / "config/level_08/unloading_rules.yaml")
    return config, UnloadingSettings.from_config(config)


def _fixture(root: Path) -> tuple[list[Item], list[Container], list[Placement], list[str]]:
    payload = yaml.safe_load((root / "config/level_08/fixtures/sequential_replay_fixture.yaml").read_text(encoding="utf-8"))
    dimensions = payload["container"]
    container = Container(dimensions["container_id"], dimensions["length_mm"], dimensions["width_mm"], dimensions["height_mm"], 100.0, 1.0, 1)
    items: list[Item] = []
    placements: list[Placement] = []
    for row in payload["items"]:
        source = {
            "delivery_priority": str(row["delivery_priority"]),
            "delivery_stop_id": row["delivery_stop_id"],
            "delivery_data_source": "sequential_fixture_v1",
            "stackability_code": "A",
            "max_stackability": "3",
            "forced_orientation": "XYZ",
        }
        items.append(Item(row["item_id"], 50.0, 80.0, 60.0, 10.0, source=source))
        placements.append(Placement(row["item_id"], "C1", row["x_mm"], row["y_mm"], row["z_mm"], 50.0, 80.0, 60.0, 10.0))
    return items, [container], placements, list(payload["expected_removal_order"])


def test_dependency_graph_and_sequential_replay_accept_supported_lifo_order(root: Path) -> None:
    config, settings = _settings(root)
    items, containers, placements, order = _fixture(root)
    dependencies = build_unloading_dependency_graph(items, placements, settings)
    result = validate_sequential_unloading(items, containers, placements, config, order)

    assert [(value.predecessor_item_id, value.successor_item_id, value.reason) for value in dependencies] == [
        ("EARLY_TOP", "EARLY_BASE", "external_support_before_supporter_removal"),
    ]
    assert result.result.valid
    assert [step.remaining_item_count for step in result.steps] == [2, 1, 0]
    assert all(step.accepted for step in result.steps)


def test_sequential_replay_rejects_removing_supporter_before_child(root: Path) -> None:
    config, _ = _settings(root)
    items, containers, placements, _ = _fixture(root)
    result = validate_sequential_unloading(items, containers, placements, config, ["EARLY_BASE", "EARLY_TOP", "LATE"])

    assert not result.result.valid
    assert any(issue.code == "SEQUENTIAL_DEPENDENCY_UNMET" for issue in result.result.issues)


def test_sequential_dependency_includes_explicit_nested_child_before_host(root: Path) -> None:
    _, settings = _settings(root)
    items, _, placements, _ = _fixture(root)
    dependencies = build_unloading_dependency_graph(
        items, placements, settings, nesting_relations=[NestingRelation("EARLY_BASE", "LATE", "C1")],
    )

    assert any(
        value.predecessor_item_id == "LATE"
        and value.successor_item_id == "EARLY_BASE"
        and value.reason == "nested_child_before_host_removal"
        for value in dependencies
    )


def test_sequential_dependency_records_later_door_blocker_as_strict_lifo_evidence(root: Path) -> None:
    _, settings = _settings(root)
    items, _, placements, _ = _fixture(root)
    blocked_layout = [
        Placement("EARLY_TOP", "C1", 100.0, 0.0, 60.0, 50.0, 80.0, 60.0, 10.0),
        Placement("EARLY_BASE", "C1", 100.0, 0.0, 0.0, 50.0, 80.0, 60.0, 10.0),
        Placement("LATE", "C1", 0.0, 0.0, 0.0, 50.0, 80.0, 60.0, 10.0),
    ]
    dependencies = build_unloading_dependency_graph(items, blocked_layout, settings)

    assert any(
        value.predecessor_item_id == "LATE"
        and value.successor_item_id == "EARLY_BASE"
        and value.reason == "later_delivery_door_blocker"
        for value in dependencies
    )


def test_sequential_replay_calls_additional_state_validator_after_each_accepted_removal(root: Path) -> None:
    config, _ = _settings(root)
    items, containers, placements, order = _fixture(root)
    observed_counts: list[int] = []

    def state_validator(remaining_items: list[Item], _remaining_placements: list[Placement]) -> ValidationResult:
        observed_counts.append(len(remaining_items))
        return ValidationResult(True, [])

    result = validate_sequential_unloading(items, containers, placements, config, order, state_validator=state_validator)

    assert result.result.valid
    assert observed_counts == [2, 1, 0]


def test_sequential_replay_composes_full_level1_to_level7_bundle_per_remaining_state(root: Path) -> None:
    unloading_config, _ = _settings(root)
    items, containers, placements, order = _fixture(root)
    level7_config = load_config(root / "config/level_08/default.yaml")
    state_validator = build_level_07_remaining_state_validator(containers, level7_config)

    result = validate_sequential_unloading(
        items, containers, placements, unloading_config, order, state_validator=state_validator,
    )

    assert result.result.valid
    assert all(step.accepted for step in result.steps)


def test_remaining_nesting_relations_are_filtered_not_reused_after_child_removal() -> None:
    relation = NestingRelation("HOST", "CHILD", "C1")

    assert filter_remaining_nesting_relations([relation], {"HOST", "CHILD"}) == (relation,)
    assert filter_remaining_nesting_relations([relation], {"HOST"}) == ()


def test_deterministic_fixture_planner_writes_isolated_plan_sequences_and_events(root: Path, tmp_path: Path) -> None:
    unloading_config, _ = _settings(root)
    simulation_config = load_config(root / "config/level_08/sequential_simulation_rules.yaml")
    settings = SequentialSimulationSettings.from_config(simulation_config)
    inherited_config = load_config(root / "config/level_08/default.yaml")
    items, containers, placements, _ = _fixture(root)
    plan = build_deterministic_fixture_plan(
        items, containers, placements,
        unloading_config=unloading_config,
        simulation_config=simulation_config,
        inherited_config=inherited_config,
    )

    assert plan.loading_order == ("LATE", "EARLY_BASE", "EARLY_TOP")
    assert plan.unloading_order == ("EARLY_TOP", "EARLY_BASE", "LATE")
    assert plan.validation.result.valid
    assert [event.sequence for event in plan.events] == list(range(len(plan.events)))
    assert [event.simulation_time_seconds for event in plan.events] == sorted(event.simulation_time_seconds for event in plan.events)

    run_dir = tmp_path / "isolated-run"
    run_dir.mkdir()
    paths = write_sequential_fixture_artifacts(run_dir, plan, items, placements, settings)
    assert {key: value.name for key, value in paths.items()} == {
        "plan": "simulation_plan.json", "events": "events.jsonl",
        "loading": "loading_sequence.csv", "unloading": "unloading_sequence.csv",
        "stops": "stop_summary.csv", "metrics": "simulation_metrics.json",
        "validation": "simulation_validation.json",
    }
    assert paths["plan"].is_file() and paths["events"].is_file()
    assert "EARLY_TOP" in paths["unloading"].read_text(encoding="utf-8")
    assert validate_sequential_fixture_artifacts(run_dir, plan, settings).valid
    with pytest.raises(FileExistsError, match="will not be overwritten"):
        write_sequential_fixture_artifacts(run_dir, plan, items, placements, settings)


def test_deterministic_planner_rejects_dependency_cycle(root: Path) -> None:
    unloading_config, _ = _settings(root)
    simulation_config = load_config(root / "config/level_08/sequential_simulation_rules.yaml")
    inherited_config = load_config(root / "config/level_08/default.yaml")
    items, containers, placements, _ = _fixture(root)
    relations = [
        NestingRelation("EARLY_BASE", "LATE", "C1"),
        NestingRelation("LATE", "EARLY_BASE", "C1"),
    ]
    with pytest.raises(ValueError, match="contains a cycle"):
        build_deterministic_fixture_plan(
            items,
            containers,
            placements,
            unloading_config=unloading_config,
            simulation_config=simulation_config,
            inherited_config=inherited_config,
            nesting_relations=relations,
        )


def test_deterministic_planner_rejects_remaining_state_cog_violation(root: Path) -> None:
    unloading_config, _ = _settings(root)
    simulation_config = load_config(root / "config/level_08/sequential_simulation_rules.yaml")
    inherited_config = load_config(root / "config/level_08/default.yaml")
    items, containers, placements, _ = _fixture(root)
    imbalanced_remaining_state = [
        value if value.item_id != "LATE" else Placement(
            value.item_id, value.container_id, 140.0, value.y_mm, value.z_mm,
            value.length_mm, value.width_mm, value.height_mm, value.weight_kg,
        )
        for value in placements
    ]
    with pytest.raises(ValueError, match="sequential validation is invalid"):
        build_deterministic_fixture_plan(
            items,
            containers,
            imbalanced_remaining_state,
            unloading_config=unloading_config,
            simulation_config=simulation_config,
            inherited_config=inherited_config,
        )


def test_deterministic_planner_rejects_initial_static_lifo_violation(root: Path) -> None:
    unloading_config, _ = _settings(root)
    simulation_config = load_config(root / "config/level_08/sequential_simulation_rules.yaml")
    inherited_config = load_config(root / "config/level_08/default.yaml")
    items, containers, _, _ = _fixture(root)
    blocked = [
        Placement("EARLY_TOP", "C1", 100.0, 0.0, 60.0, 50.0, 80.0, 60.0, 10.0),
        Placement("EARLY_BASE", "C1", 100.0, 0.0, 0.0, 50.0, 80.0, 60.0, 10.0),
        Placement("LATE", "C1", 0.0, 0.0, 0.0, 50.0, 80.0, 60.0, 10.0),
    ]
    with pytest.raises(ValueError, match="initial static strict-LIFO"):
        build_deterministic_fixture_plan(
            items,
            containers,
            blocked,
            unloading_config=unloading_config,
            simulation_config=simulation_config,
            inherited_config=inherited_config,
        )
