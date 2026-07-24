from __future__ import annotations

import json
from pathlib import Path

from container_packing.data_loader import load_config
from container_packing.levels.level_06_pipeline import validate_level_06_bundle
from container_packing.levels.nesting_engine import NestingRelation
from container_packing.reporting import write_run_outputs
from container_packing.schemas import Container, Item, Placement


def _fixture() -> tuple[list[Item], list[Container], list[Placement], list[NestingRelation]]:
    host_source = {
        "stackability_code": "A", "max_stackability": "3",
        "nesting_group_id": "G1", "nesting_role": "host",
        "inner_length_mm": "110", "inner_width_mm": "100", "inner_height_mm": "90",
        "max_nesting_depth": "1", "nesting_data_source": "fixture_v1",
    }
    child_source = {
        "stackability_code": "A", "max_stackability": "3",
        "nesting_group_id": "G1", "nesting_role": "child",
        "nesting_increment_height_mm": "20", "nesting_data_source": "fixture_v1",
    }
    items = [
        Item("HOST", 100, 90, 80, 10, source=host_source),
        Item("CHILD", 100, 90, 70, 10, source=child_source),
    ]
    containers = [Container("C1", 200, 100, 250, 500, 1, volume_m3=0.005)]
    placements = [
        Placement("HOST", "C1", 0, 0, 0, 100, 90, 80, 10, "XYZ"),
        Placement("CHILD", "C1", 0, 0, 80, 100, 90, 70, 10, "XYZ"),
    ]
    return items, containers, placements, [NestingRelation("HOST", "CHILD", "C1")]


def test_level6_fixture_pipeline_composes_level5_and_nesting(root: Path) -> None:
    items, containers, placements, relations = _fixture()
    config = load_config(root / "config/level_06/default.yaml")

    bundle = validate_level_06_bundle(items, containers, placements, config, relations)

    assert bundle.result.valid
    assert {"compound_support.csv", "stacks.csv", "load_bearing.csv", "load_transfer.csv"} <= set(bundle.solution_tables)
    assert {"nesting_relations.csv", "nesting_height.csv", "nesting_compounds.csv"} <= set(bundle.solution_tables)
    assert {"nesting_validation.json", "compound_geometry_validation.json"} <= set(bundle.validation_documents)
    assert "support.csv" not in bundle.solution_tables
    child = next(row for row in bundle.solution_tables["nesting_height.csv"] if row["item_id"] == "CHILD")
    assert child["chain_effective_height_mm"] == 100
    assert bundle.metadata["nesting_runtime_enabled"] is False
    assert bundle.metadata["nesting_relation_count"] == 1
    assert bundle.scene_item_metadata["CHILD"]["nesting_host_item_id"] == "HOST"


def test_level6_fixture_pipeline_keeps_level5_validation_and_rejects_bad_relation(root: Path) -> None:
    items, containers, placements, _ = _fixture()
    config = load_config(root / "config/level_06/default.yaml")
    items[1] = Item(
        "CHILD", 100, 90, 70, 10,
        source={**items[1].source, "nesting_group_id": "OTHER"},
    )

    bundle = validate_level_06_bundle(
        items, containers, placements, config, [NestingRelation("HOST", "CHILD", "C1")]
    )

    assert not bundle.result.valid
    assert not bundle.solution_tables["nesting_height.csv"]
    assert bundle.validation_documents["nesting_validation.json"]["valid"] is False
    assert {issue.code for issue in bundle.result.issues} == {"NESTING_RELATION_INVALID"}


def test_level6_fixture_bundle_writes_isolated_nesting_artifacts(root: Path, tmp_path: Path) -> None:
    items, containers, placements, relations = _fixture()
    config = load_config(root / "config/level_06/default.yaml")
    bundle = validate_level_06_bundle(items, containers, placements, config, relations)
    items_path = tmp_path / "items.csv"
    containers_path = tmp_path / "containers.csv"
    items_path.write_text("fixture items\n", encoding="utf-8")
    containers_path.write_text("fixture containers\n", encoding="utf-8")
    run_dir = tmp_path / "outputs" / "level_06" / "runs" / "fixture"
    run_dir.mkdir(parents=True)
    metadata = {
        "level_id": "level_06", "run_id": "fixture", "algorithm_id": "fixture_validation",
        "solver": "none", "environment": "local", "instance_id": "level_06_fixture",
        "random_seed": 42, "status": "FEASIBLE", "n_items": 2, "n_containers": 1,
        "algorithm_runtime_seconds": 0.0, "objective_value": None,
        "selected_containers": ["C1"], "algorithm_role": "validation_fixture",
        **bundle.metadata,
    }

    write_run_outputs(
        run_dir, placements, containers, metadata, bundle.result, config,
        items_path=items_path, containers_path=containers_path, project_root=root,
        extra_solution_tables=bundle.solution_tables,
        extra_validation_documents=bundle.validation_documents,
        solution_payload_extra=bundle.solution_payload_extra,
        scene_item_metadata=bundle.scene_item_metadata,
        extra_report_lines=bundle.extra_report_lines,
    )

    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    metrics = json.loads((run_dir / "metrics" / "metrics.json").read_text(encoding="utf-8"))
    solution = json.loads((run_dir / "solution" / "solution.json").read_text(encoding="utf-8"))
    assert (run_dir / "solution" / "nesting_relations.csv").is_file()
    assert (run_dir / "solution" / "nesting_height.csv").is_file()
    assert (run_dir / "validation" / "nesting_validation.json").is_file()
    assert manifest["level"] == "level_06"
    assert manifest["nesting_contract_version"] == 1
    assert manifest["compound_geometry_model"] == "compound_root_effective_envelope_geometry_v1"
    assert metrics["nesting_runtime_enabled"] is False
    assert metrics["compound_count"] == 1
    assert solution["nesting"]["model"] == "compound_root_effective_envelope_geometry_v1"


def test_level6_bundle_uses_compound_not_raw_child_geometry_for_stack_and_load(root: Path) -> None:
    items, containers, placements, relations = _fixture()
    items.append(Item(
        "TOP", 100, 90, 40, 5,
        source={"stackability_code": "A", "max_stackability": "3"},
    ))
    placements.append(Placement("TOP", "C1", 0, 0, 100, 100, 90, 40, 5, "XYZ"))
    config = load_config(root / "config/level_06/default.yaml")

    bundle = validate_level_06_bundle(items, containers, placements, config, relations)

    # Raw CHILD spans z=80..150 and overlaps TOP at z=100, whereas the
    # external HOST compound ends at z=100 and supports TOP correctly.
    assert bundle.result.valid
    assert [row["item_id"] for row in bundle.solution_tables["load_bearing.csv"]] == ["HOST", "TOP"]
    assert bundle.solution_tables["load_transfer.csv"][0]["supporter_item_id"] == "HOST"
    top_stack = next(row for row in bundle.solution_tables["stacks.csv"] if row["item_id"] == "TOP")
    assert top_stack["direct_parent_item_id"] == "HOST"
