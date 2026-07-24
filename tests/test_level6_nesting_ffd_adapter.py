from __future__ import annotations

import json
from pathlib import Path

from container_packing.data_loader import load_config
from container_packing.levels.level_06_compound_policy import build_level_06_compound_fixture_policy
from container_packing.levels.level_06_ffd_adapter import solve_nesting_aware_ffd_fixture
from container_packing.levels.level_06_fixture_output import write_nesting_aware_ffd_fixture_run
from container_packing.schemas import Container, Item, Placement


def _fixture() -> tuple[list[Item], list[Container]]:
    items = [
        Item(
            "HOST", 100, 90, 80, 10,
            source={
                "stackability_code": "A", "max_stackability": "3",
                "nesting_group_id": "G1", "nesting_role": "host",
                "inner_length_mm": "110", "inner_width_mm": "100", "inner_height_mm": "90",
                "max_nesting_depth": "1", "nesting_data_source": "fixture_v1",
            },
        ),
        Item(
            "CHILD", 100, 90, 70, 10,
            source={
                "stackability_code": "A", "max_stackability": "3",
                "nesting_group_id": "G1", "nesting_role": "child",
                "nesting_increment_height_mm": "20", "nesting_data_source": "fixture_v1",
            },
        ),
    ]
    return items, [Container("C1", 200, 100, 250, 500, 1, volume_m3=0.005)]


def test_fixture_adapter_packs_one_compound_and_validates_expanded_members(root: Path) -> None:
    items, containers = _fixture()
    result = solve_nesting_aware_ffd_fixture(
        items, containers, load_config(root / "config/level_06/default.yaml")
    )

    assert result.outcome.solve.status == "FEASIBLE"
    assert result.construction.accepted_relation_count == 1
    assert [(value.host_item_id, value.child_item_id, value.container_id) for value in result.relations] == [
        ("HOST", "CHILD", "C1")
    ]
    assert result.projection is not None
    assert len(result.projection.compounds) == 1
    assert result.projection.compounds[0].effective_height_mm == 100
    assert result.validation is not None and result.validation.result.valid
    assert result.outcome.metadata["compound_validation_status"] == "VALID"
    assert result.outcome.metadata["feasibility_policy"] == (
        "level_06_compound_geometry_payload_exact_support_stackability_load_bearing"
    )
    assert result.outcome.metadata["support_valid_candidates"] >= 1
    placements = {value.item_id: value for value in result.placements}
    assert placements["CHILD"].container_id == placements["HOST"].container_id
    assert (placements["CHILD"].x_mm, placements["CHILD"].y_mm, placements["CHILD"].z_mm) == (
        placements["HOST"].x_mm, placements["HOST"].y_mm, placements["HOST"].z_mm,
    )


def test_fixture_adapter_is_deterministic_and_does_not_register_runtime(root: Path) -> None:
    items, containers = _fixture()
    first = solve_nesting_aware_ffd_fixture(
        items, containers, load_config(root / "config/level_06/default.yaml")
    )
    second = solve_nesting_aware_ffd_fixture(
        list(reversed(items)), containers, load_config(root / "config/level_06/default.yaml")
    )

    assert first.relations == second.relations
    assert [value.to_dict() for value in first.projection.compounds] == [
        value.to_dict() for value in second.projection.compounds
    ]
    assert first.outcome.metadata["nesting_runtime_enabled"] is False


def test_compound_policy_rejects_a_floating_external_candidate(root: Path) -> None:
    items, containers = _fixture()
    compound_root = Item("HOST", 100, 90, 100, 20, source=items[0].source)
    policy = build_level_06_compound_fixture_policy(
        [compound_root], load_config(root / "config/level_06/default.yaml")
    )
    floating = Placement("HOST", "C1", 0, 0, 1, 100, 90, 100, 20, "XYZ")

    assert not policy.allows(containers[0], [], floating, loaded_weight_kg=0, tolerance=1e-6)
    assert policy.metadata()["support_rejected_candidates"] == 1


def test_fixture_adapter_writes_isolated_compound_artifacts(root: Path, tmp_path: Path) -> None:
    items, containers = _fixture()
    config = load_config(root / "config/level_06/default.yaml")
    result = solve_nesting_aware_ffd_fixture(items, containers, config)
    items_path = tmp_path / "items.csv"
    containers_path = tmp_path / "containers.csv"
    items_path.write_text("fixture items\n", encoding="utf-8")
    containers_path.write_text("fixture containers\n", encoding="utf-8")
    run_dir = tmp_path / "outputs" / "level_06" / "runs" / "adapter_fixture"

    write_nesting_aware_ffd_fixture_run(
        run_dir, result, containers, config,
        items_path=items_path, containers_path=containers_path, project_root=root,
        run_id="adapter_fixture",
    )

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    solver = json.loads((run_dir / "solver" / "solver_summary.json").read_text(encoding="utf-8"))
    metrics = json.loads((run_dir / "metrics" / "metrics.json").read_text(encoding="utf-8"))
    assert manifest["level"] == "level_06"
    assert manifest["fixture_adapter"] == "level_06_nesting_aware_ffd_compound_v1"
    assert manifest["nesting_construction_policy"] == "explicit_nesting_best_fit_chain_v1"
    assert solver["compound_validation_status"] == "VALID"
    assert metrics["nesting_accepted_relation_count"] == 1
    assert (run_dir / "solution" / "nesting_compounds.csv").is_file()
    assert (run_dir / "validation" / "compound_geometry_validation.json").is_file()

    try:
        write_nesting_aware_ffd_fixture_run(
            run_dir, result, containers, config,
            items_path=items_path, containers_path=containers_path, project_root=root,
            run_id="adapter_fixture",
        )
    except FileExistsError:
        pass
    else:
        raise AssertionError("fixture writer must refuse to overwrite an existing run")
