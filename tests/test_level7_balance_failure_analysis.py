from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path


def _module():
    path = Path(__file__).parents[1] / "scripts" / "analyze_level7_balance_failures.py"
    spec = importlib.util.spec_from_file_location("level7_analysis", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_analysis_identifies_axis_direction_and_writes_reports(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    benchmark = root / "outputs" / "level_07" / "runs" / "benchmark"
    source = root / "outputs" / "level_07" / "runs" / "source"
    (benchmark / "benchmark").mkdir(parents=True)
    (source / "solver").mkdir(parents=True)
    (source / "validation").mkdir(parents=True)
    (source / "solution").mkdir(parents=True)
    with (benchmark / "benchmark" / "results.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "status", "scenario_id", "algorithm", "item_count", "container_count",
            "input_fingerprint", "experiment_run_dir", "used_container_count",
        ])
        writer.writeheader()
        writer.writerow({
            "status": "INVALID_SOLUTION", "scenario_id": "scale", "algorithm": "best_fit",
            "item_count": "300", "container_count": "25", "input_fingerprint": "abc",
            "experiment_run_dir": "outputs/level_07/runs/source", "used_container_count": "5",
        })
    (source / "solver" / "solver_summary.json").write_text(json.dumps({
        "algorithm_runtime_seconds": 4.0,
        "balance_repair_termination_reason": "candidate_limit",
        "balance_lns_termination_reason": "no_improving_valid_neighborhood",
    }), encoding="utf-8")
    (source / "validation" / "balance_validation.json").write_text(json.dumps({
        "records": [{
            "container_id": "C1", "signed_longitudinal_offset_ratio": 0.02,
            "max_longitudinal_offset_ratio": 0.15, "signed_lateral_offset_ratio": -0.18,
            "max_lateral_offset_ratio": 0.15,
        }]
    }), encoding="utf-8")
    (source / "solution" / "placements.csv").write_text(
        "item_id,container_id,x_mm,y_mm,z_mm,length_mm,width_mm,height_mm,weight_kg\n"
        "I1,C1,0,0,0,10,10,10,50\n"
        "I2,C1,50,20,0,10,10,10,10\n",
        encoding="utf-8",
    )
    (source / "solution" / "stacks.csv").write_text(
        "item_id,container_id,direct_parent_item_id\nI1,C1,\nI2,C1,\n",
        encoding="utf-8",
    )

    module = _module()
    document = module.analyse_benchmark(benchmark)
    violation = document["invalid_runs"][0]["dominant_failure"]

    assert violation == {
        "container_id": "C1", "axis": "lateral", "signed_offset_ratio": -0.18,
        "limit_ratio": 0.15, "excess_ratio": 0.03,
        "needed_mass_shift_direction": "increase_y",
    }
    assert document["invalid_runs"][0]["repair_classification"]["category"] == (
        "targeted_local_repair_candidate"
    )
    comparison = module.compare_analyses(document, document)
    assert comparison[0]["max_excess_delta"] == 0.0
    json_path, markdown_path = module.write_report(document, benchmark / "reports")
    assert json_path.is_file()
    assert markdown_path.is_file()
