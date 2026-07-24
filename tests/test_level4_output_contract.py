from __future__ import annotations

import json
from pathlib import Path

from container_packing.levels.stackability import StackRecord, report_lines, scene_item_metadata, solution_payload
from container_packing.reporting import write_run_outputs
from container_packing.schemas import Container, Placement, ValidationResult


def test_level4_stack_metadata_is_exportable_to_solution_report_and_scene(root: Path, tmp_path: Path) -> None:
    placements = [
        Placement("BOTTOM", "C", 0, 0, 0, 10, 10, 5, 1),
        Placement("TOP", "C", 0, 0, 5, 10, 10, 5, 1),
    ]
    containers = [Container("C", 10, 10, 10, 10, 1, volume_m3=1e-6)]
    records = [
        StackRecord("BOTTOM", "C", None, "C::BOTTOM", 0, 2, 2),
        StackRecord("TOP", "C", "BOTTOM", "C::BOTTOM", 1, 2, 2),
    ]
    items_path = tmp_path / "items.csv"
    containers_path = tmp_path / "containers.csv"
    items_path.write_text("item fixture\n", encoding="utf-8")
    containers_path.write_text("container fixture\n", encoding="utf-8")
    run_dir = tmp_path / "outputs" / "level_04" / "runs" / "fixture"
    run_dir.mkdir(parents=True)
    metadata = {
        "level_id": "level_04", "run_id": "fixture", "algorithm_id": "fixture",
        "solver": "fixture", "environment": "local", "instance_id": "fixture",
        "random_seed": 42, "status": "FEASIBLE", "n_items": 2, "n_containers": 1,
        "algorithm_runtime_seconds": 0.0, "objective_value": 1.0,
        "selected_containers": ["C"], "algorithm_role": "fixture",
    }

    write_run_outputs(
        run_dir, placements, containers, metadata, ValidationResult(True, []), {},
        items_path=items_path, containers_path=containers_path, project_root=root,
        extra_solution_tables={"stacks.csv": [record.to_dict() for record in records]},
        solution_payload_extra={"stackability": solution_payload(records)},
        scene_item_metadata=scene_item_metadata(records),
        extra_report_lines=report_lines(records),
    )

    solution = json.loads((run_dir / "solution" / "solution.json").read_text(encoding="utf-8"))
    scene = json.loads((run_dir / "visualization" / "scene.json").read_text(encoding="utf-8"))
    report = (run_dir / "reports" / "summary.md").read_text(encoding="utf-8")
    scene_top = next(item for item in scene["containers"][0]["items"] if item["item_id"] == "TOP")
    assert solution["stackability"]["stack_count"] == 1
    assert solution["stackability"]["maximum_stack_depth"] == 1
    assert (run_dir / "solution" / "stacks.csv").is_file()
    assert scene_top["metadata"]["direct_parent_item_id"] == "BOTTOM"
    assert scene_top["metadata"]["stack_depth"] == 1
    assert "Stack count: 1" in report
