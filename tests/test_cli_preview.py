from scipy.optimize import OptimizeResult

from container_packing.cli import terminal_preview
from container_packing.schemas import Placement, RunResult, SolveResult, ValidationResult


def test_terminal_preview_contains_summary_and_limits_placements():
    placements = [
        Placement(f"I{i:04d}", "C01", float(i), 0, 0, 10, 20, 30, 2)
        for i in range(1, 4)
    ]
    result = RunResult(
        solve=SolveResult("OPTIMAL", "ok", 100, None, OptimizeResult()),
        placements=placements,
        validation=ValidationResult(True, []),
        metadata={
            "status": "OPTIMAL", "level_id": "level_01", "algorithm_id": "milp_big_m",
            "n_items": 3, "n_containers": 2, "container_count": 1,
            "selected_containers": ["C01"], "objective_value": 100,
            "algorithm_runtime_seconds": 0.25, "run_dir": "outputs/level_01/runs/example",
        },
    )
    preview = terminal_preview(result, placement_limit=2)
    assert "Validation   : VALID" in preview
    assert "C01" in preview
    assert "I0001" in preview and "I0002" in preview
    assert "I0003" not in preview
    assert "1 rows hidden" in preview


def test_validate_cli_rejects_level_mismatch(root, tmp_path):
    import json
    from container_packing.cli import main

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "manifest.json").write_text(json.dumps({"level": "level_01"}), encoding="utf-8")
    assert main(["validate", "--level", "level_02", "--run-dir", str(run_dir)]) == 2
