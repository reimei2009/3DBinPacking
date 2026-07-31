from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from container_packing.data_loader import load_config
from container_packing.algorithms.feasibility import FixedOrientationFeasibilityPolicy
from container_packing.levels.level_08_delivery_repair import DeliveryRepairEngine
from container_packing.levels.level_08_delivery_scoring import (
    SequentialBalanceFeasibilityPolicy,
    StrictLifoFeasibilityPolicy,
)
from container_packing.levels.level_08_fixture_output import write_level_08_fixture_validation_run
from container_packing.levels.level_08_validation import validate_unloading_lifo
from container_packing.levels.unloading import (
    UnloadingSettings, assess_unloading_accessibility, prospective_direct_rehandle_delta,
)
from container_packing.schemas import Container, Item, Placement


def _config(root: Path) -> dict:
    return load_config(root / "config/level_08/unloading_rules.yaml")


def _items() -> list[Item]:
    return [
        Item("EARLY", 100, 80, 60, 10, source={"delivery_priority": "1", "delivery_stop_id": "A", "delivery_data_source": "fixture"}),
        Item("LATE", 100, 80, 60, 10, source={"delivery_priority": "2", "delivery_stop_id": "B", "delivery_data_source": "fixture"}),
    ]


def _containers() -> list[Container]:
    return [Container("C1", 400, 100, 100, 1000, 100, volume_m3=0.004)]


def _placement(item_id: str, x_mm: float) -> Placement:
    return Placement(item_id, "C1", x_mm, 0, 0, 100, 80, 60, 10)


def test_independent_validator_accepts_lifo_valid_layout_and_emits_empty_rehandle_plan(root: Path) -> None:
    validation = validate_unloading_lifo(_items(), [_placement("EARLY", 0), _placement("LATE", 100)], _config(root))

    assert validation.result.valid
    assert validation.records[1].blocking_item_ids == ("EARLY",)
    assert validation.records[1].lifo_compliant
    assert validation.rehandle_rows() == []
    assert validation.payload()["model"] == "straight_path_static_lifo_v1"


def test_independent_validator_rejects_later_priority_blocker_and_records_rehandle(root: Path) -> None:
    validation = validate_unloading_lifo(_items(), [_placement("EARLY", 100), _placement("LATE", 0)], _config(root))

    assert not validation.result.valid
    assert [issue.code for issue in validation.result.issues] == ["LIFO_LATER_PRIORITY_BLOCKER"]
    assert validation.rehandle_rows() == [{
        "target_item_id": "EARLY", "container_id": "C1", "target_delivery_priority": 1,
        "blocker_item_id": "LATE", "blocker_relation": "later_delivery_priority_direct_path_blocker",
        "rehandle_rank": 1, "counting_model": "direct_later_priority_blockers_v1",
    }]


def test_prospective_delta_matches_new_candidate_lifo_pairs(root: Path) -> None:
    items = _items()
    settings = UnloadingSettings.from_config(_config(root))
    existing = [_placement("EARLY", 100)]
    candidate = _placement("LATE", 0)

    delta = prospective_direct_rehandle_delta({item.item_id: item for item in items}, existing, candidate, settings)
    complete = assess_unloading_accessibility(items, [*existing, candidate], settings)

    assert delta == (1, 1)
    assert sum(record.minimum_rehandle_count for record in complete) == 1


def test_strict_lifo_feasibility_rejects_later_item_in_front(root: Path) -> None:
    items = _items()
    policy = StrictLifoFeasibilityPolicy(
        {item.item_id: item for item in items},
        UnloadingSettings.from_config(_config(root)),
        FixedOrientationFeasibilityPolicy(),
    )
    container = Container("C1", 500, 80, 60, 100, 1)

    assert not policy.allows(
        container,
        [_placement("EARLY", 200)],
        _placement("LATE", 0),
        loaded_weight_kg=10,
        tolerance=1e-6,
    )
    assert policy.metadata()["strict_lifo_rejected_candidates"] == 1


def test_strict_lifo_feasibility_accepts_early_item_in_front(root: Path) -> None:
    items = _items()
    policy = StrictLifoFeasibilityPolicy(
        {item.item_id: item for item in items},
        UnloadingSettings.from_config(_config(root)),
        FixedOrientationFeasibilityPolicy(),
    )
    container = Container("C1", 500, 80, 60, 100, 1)

    assert policy.allows(
        container,
        [_placement("LATE", 200)],
        _placement("EARLY", 0),
        loaded_weight_kg=10,
        tolerance=1e-6,
    )
    assert policy.metadata()["strict_lifo_valid_candidates"] == 1


def test_reverse_loading_balance_policy_keeps_level7_band_hard(
    root: Path,
) -> None:
    policy = SequentialBalanceFeasibilityPolicy(
        load_config(root / "config/level_07/balance_rules.yaml"),
        FixedOrientationFeasibilityPolicy(),
    )
    container = Container("C1", 500, 80, 60, 100, 1)

    assert not policy.allows(
        container,
        [],
        _placement("EARLY", 0),
        loaded_weight_kg=0,
        tolerance=1e-6,
    )
    assert policy.allows(
        container,
        [],
        _placement("EARLY", 200),
        loaded_weight_kg=0,
        tolerance=1e-6,
    )
    metadata = policy.metadata()
    assert metadata["sequential_balance_rejected_candidates"] == 1
    assert metadata["sequential_balance_valid_candidates"] == 1


def test_bounded_local_delivery_repair_moves_later_blocker_without_full_repack(root: Path) -> None:
    items = _items()
    settings = UnloadingSettings.from_config(_config(root))
    initial = [_placement("EARLY", 100), _placement("LATE", 0)]
    engine = DeliveryRepairEngine(
        policy=FixedOrientationFeasibilityPolicy(), settings=settings,
        coordinate_tolerance_mm=1e-6, support_epsilon_mm=1e-6,
        max_candidates=32, contributor_limit=2,
    )
    result = engine.repair(
        items, _containers(), initial,
        validate_inherited=lambda placements: True,
        validate_final=lambda placements: validate_unloading_lifo(items, placements, _config(root)).result.valid,
        fixed_seconds=1.0, extra_seconds=0.0, extra_container=None,
    )

    assert result.placements is not None
    assert result.stats.initial_rehandles == 1
    assert result.stats.final_rehandles == 0
    assert "relocate" in result.stats.accepted_moves


def test_delivery_repair_reserves_swap_operator_budget(root: Path) -> None:
    items = _items()
    settings = UnloadingSettings.from_config(_config(root))
    engine = DeliveryRepairEngine(
        policy=FixedOrientationFeasibilityPolicy(), settings=settings,
        coordinate_tolerance_mm=1e-6, support_epsilon_mm=1e-6,
        max_candidates=16, contributor_limit=2,
        relocation_transfer_max_candidates=0, swap_max_candidates=16,
        neighborhood_max_candidates=0,
    )
    result = engine.repair(
        items, _containers(), [_placement("EARLY", 100), _placement("LATE", 0)],
        validate_inherited=lambda placements: True,
        validate_final=lambda placements: validate_unloading_lifo(items, placements, _config(root)).result.valid,
        fixed_seconds=1.0, extra_seconds=0.0, extra_container=None,
    )

    assert result.placements is not None
    assert result.stats.swap_candidates > 0
    assert result.stats.accepted_moves == ["swap"]


def test_validator_requires_explicit_delivery_metadata(root: Path) -> None:
    undecided = [Item("A", 100, 80, 60, 10)]
    validation = validate_unloading_lifo(undecided, [_placement("A", 0)], _config(root))

    assert not validation.result.valid
    assert validation.result.issues[0].code == "UNLOADING_INPUT_INVALID"
    assert "unloading is disabled" in validation.result.issues[0].message


def test_fixture_writer_isolated_and_persists_all_level8_artifacts(root: Path, tmp_path: Path) -> None:
    items = _items()
    containers = _containers()
    placements = [_placement("EARLY", 0), _placement("LATE", 100)]
    validation = validate_unloading_lifo(items, placements, _config(root))
    items_path = tmp_path / "items.csv"
    containers_path = tmp_path / "containers.csv"
    items_path.write_text("fixture items\n", encoding="utf-8")
    containers_path.write_text("fixture containers\n", encoding="utf-8")
    run_dir = tmp_path / "outputs" / "level_08" / "runs" / "lifo_valid_fixture"

    metadata = write_level_08_fixture_validation_run(
        run_dir, items, containers, placements, validation, _config(root),
        items_path=items_path, containers_path=containers_path, project_root=root,
        run_id="lifo_valid_fixture", fixture_id="level_08_lifo_valid_fixture_v1",
    )

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    document = json.loads((run_dir / "validation" / "unloading_validation.json").read_text(encoding="utf-8"))
    accessibility = pd.read_csv(run_dir / "solution" / "unloading_accessibility.csv")
    rehandles = pd.read_csv(run_dir / "solution" / "rehandle_plan.csv")
    assert metadata["status"] == "VALIDATION_ONLY"
    assert manifest["level"] == "level_08"
    assert manifest["unloading_model"] == "straight_path_static_lifo_v1"
    assert manifest["door_face"] == "x_min"
    assert document["valid"] is True
    assert len(accessibility) == 2
    assert list(rehandles.columns) == [
        "target_item_id", "container_id", "target_delivery_priority", "blocker_item_id",
        "blocker_relation", "rehandle_rank", "counting_model",
    ]
    assert rehandles.empty
    for artifact in (
        run_dir / "solution" / "unloading_accessibility.csv",
        run_dir / "solution" / "rehandle_plan.csv",
        run_dir / "validation" / "unloading_validation.json",
    ):
        assert artifact.is_file()

    try:
        write_level_08_fixture_validation_run(
            run_dir, items, containers, placements, validation, _config(root),
            items_path=items_path, containers_path=containers_path, project_root=root,
            run_id="lifo_valid_fixture", fixture_id="level_08_lifo_valid_fixture_v1",
        )
    except FileExistsError:
        pass
    else:
        raise AssertionError("Level 8 fixture writer must refuse to overwrite a run")
