from __future__ import annotations

import json
from pathlib import Path

from container_packing.data_loader import load_config
from container_packing.levels.level_07_candidate_contract import load_runtime_candidate_contract
from container_packing.levels.level_07_fixture_bundle import validate_level_07_fixture_bundle
from container_packing.levels.level_07_fixture_output import write_level_07_fixture_bundle_run
from container_packing.levels.nesting_engine import NestingRelation
from container_packing.schemas import Container, Item, Placement


def _config(root: Path) -> dict:
    return load_config(
        root / "config/level_07/fixtures/declared_nesting_multi_compound_balance_fixture.yaml"
    )


def _items() -> list[Item]:
    stack = {"stackability_code": "A", "max_stackability": "3", "nesting_data_source": "fixture"}
    return [
        Item("ROOT-001", 240, 180, 120, 120, source={
            **stack, "nesting_group_id": "G1", "nesting_role": "host",
            "inner_length_mm": "220", "inner_width_mm": "160", "inner_height_mm": "110",
            "max_nesting_depth": "2",
        }),
        Item("MIDDLE-001", 210, 150, 100, 100, source={
            **stack, "nesting_group_id": "G1", "nesting_role": "both",
            "inner_length_mm": "190", "inner_width_mm": "140", "inner_height_mm": "90",
            "max_nesting_depth": "2", "nesting_increment_height_mm": "25",
        }),
        Item("CHILD-001", 180, 130, 80, 80, source={
            **stack, "nesting_group_id": "G1", "nesting_role": "child",
            "nesting_increment_height_mm": "20",
        }),
        Item("TOP-001", 150, 160, 80, 50, source={
            **stack, "nesting_group_id": "", "nesting_role": "none",
        }),
    ]


def _containers() -> list[Container]:
    return [Container("C1", 240, 180, 300, 500, 100, volume_m3=0.01296)]


def _placements(*, top_z_mm: float = 165.0) -> list[Placement]:
    return [
        Placement("ROOT-001", "C1", 0, 0, 0, 240, 180, 120, 120),
        Placement("MIDDLE-001", "C1", 0, 0, 0, 210, 150, 100, 100),
        Placement("CHILD-001", "C1", 0, 0, 0, 180, 130, 80, 80),
        Placement("TOP-001", "C1", 0, 0, top_z_mm, 150, 160, 80, 50),
    ]


def _relations() -> list[NestingRelation]:
    return [
        NestingRelation("ROOT-001", "MIDDLE-001", "C1"),
        NestingRelation("MIDDLE-001", "CHILD-001", "C1"),
    ]


def test_level7_fixture_bundle_composes_level6_and_balance_evidence(root: Path) -> None:
    bundle = validate_level_07_fixture_bundle(
        _items(), _containers(), _placements(), _config(root), _relations()
    )

    assert bundle.result.valid
    assert set(bundle.solution_tables) >= {
        "nesting_relations.csv", "nesting_compounds.csv", "compound_support.csv",
        "stacks.csv", "load_bearing.csv", "load_transfer.csv", "center_of_mass.csv",
    }
    assert set(bundle.validation_documents) >= {
        "nesting_validation.json", "compound_geometry_validation.json",
        "stack_validation.json", "load_bearing_validation.json", "balance_validation.json",
    }
    record = bundle.solution_tables["center_of_mass.csv"][0]
    assert record["total_weight_kg"] == 350
    assert record["balanced"] is True
    assert record["longitudinal_ratio"] > 0.47
    assert record["longitudinal_ratio"] < 0.48
    assert bundle.metadata["level_07_fixture_validation_only"] is True
    assert bundle.metadata["balance_validation_status"] == "VALID"
    assert bundle.metadata["load_transfer_edge_count"] == 1
    assert bundle.validation_documents["balance_validation.json"]["valid"] is True


def test_level7_bundle_rejects_balance_without_discarding_inherited_evidence(root: Path) -> None:
    config = _config(root)
    balance = load_config(root / "config/level_07/balance_rules.yaml")
    balance["balance_profile"]["overrides"] = [{
        "container_id": "C1",
        "max_longitudinal_offset_ratio": 0.01,
        "max_lateral_offset_ratio": 0.01,
        "balance_profile_source": "strict_fixture",
    }]
    config["balance"] = balance

    bundle = validate_level_07_fixture_bundle(
        _items(), _containers(), _placements(), config, _relations()
    )

    assert bundle.result.valid is False
    assert bundle.metadata["balance_validation_status"] == "INVALID"
    assert bundle.solution_tables["load_transfer.csv"]
    assert bundle.solution_tables["center_of_mass.csv"]
    assert {
        issue.code for issue in bundle.result.issues
    } == {"LONGITUDINAL_CENTER_OF_MASS_OUT_OF_BAND"}


def test_level7_bundle_does_not_evaluate_balance_when_level6_is_invalid(root: Path) -> None:
    bundle = validate_level_07_fixture_bundle(
        _items(), _containers(), _placements(top_z_mm=0), _config(root), _relations()
    )

    assert bundle.result.valid is False
    assert bundle.metadata["balance_validation_status"] == "NOT_EVALUATED"
    assert "center_of_mass.csv" not in bundle.solution_tables
    assert bundle.validation_documents["balance_validation.json"]["status"] == (
        "not_evaluated_due_to_invalid_level_06_bundle"
    )


def test_level7_fixture_writer_isolated_and_persists_balance_artifacts(
    root: Path, tmp_path: Path
) -> None:
    items = _items()
    containers = _containers()
    placements = _placements()
    config = _config(root)
    bundle = validate_level_07_fixture_bundle(
        items, containers, placements, config, _relations()
    )
    items_path = tmp_path / "items.csv"
    containers_path = tmp_path / "containers.csv"
    items_path.write_text("fixture items\n", encoding="utf-8")
    containers_path.write_text("fixture containers\n", encoding="utf-8")
    run_dir = tmp_path / "outputs" / "level_07" / "runs" / "balance_fixture"

    write_level_07_fixture_bundle_run(
        run_dir, items, containers, placements, bundle, config,
        items_path=items_path, containers_path=containers_path, project_root=root,
        run_id="balance_fixture",
    )

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    solver = json.loads((run_dir / "solver" / "solver_summary.json").read_text(encoding="utf-8"))
    metrics = json.loads((run_dir / "metrics" / "metrics.json").read_text(encoding="utf-8"))
    balance = json.loads((run_dir / "validation" / "balance_validation.json").read_text(encoding="utf-8"))
    assert manifest["level"] == "level_07"
    assert manifest["center_of_mass_model"] == "mass_weighted_item_geometric_center_v1"
    assert manifest["balance_validation_status"] == "VALID"
    assert solver["balanced_container_count"] == 1
    assert metrics["balance_profile"] == "symmetric_center_band_v1"
    assert balance["valid"] is True
    candidate_config = load_config(root / "config/level_07/runtime_candidate.yaml")
    load_runtime_candidate_contract(candidate_config)
    output = candidate_config["runtime_candidate"]["output"]
    for filename in output["required_solution_tables"]:
        assert (run_dir / "solution" / filename).is_file()
    for filename in output["required_validation_documents"]:
        assert (run_dir / "validation" / filename).is_file()

    second_run_dir = tmp_path / "outputs" / "level_07" / "runs" / "balance_fixture_repeat"
    write_level_07_fixture_bundle_run(
        second_run_dir, items, containers, placements, bundle, config,
        items_path=items_path, containers_path=containers_path, project_root=root,
        run_id="balance_fixture_repeat",
    )
    assert (run_dir / "solution" / "center_of_mass.csv").read_bytes() == (
        second_run_dir / "solution" / "center_of_mass.csv"
    ).read_bytes()
    assert (run_dir / "validation" / "balance_validation.json").read_bytes() == (
        second_run_dir / "validation" / "balance_validation.json"
    ).read_bytes()

    try:
        write_level_07_fixture_bundle_run(
            run_dir, items, containers, placements, bundle, config,
            items_path=items_path, containers_path=containers_path, project_root=root,
            run_id="balance_fixture",
        )
    except FileExistsError:
        pass
    else:
        raise AssertionError("fixture writer must refuse to overwrite an existing run")
