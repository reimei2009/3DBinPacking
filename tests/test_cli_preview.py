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
            "algorithm_role": "exact_reference",
            "n_items": 3, "n_containers": 2, "container_count": 1,
            "selected_containers": ["C01"], "objective_value": 100,
            "algorithm_runtime_seconds": 0.25, "run_dir": "outputs/level_01/runs/example",
            "mip_gap": 0.125, "mip_dual_bound": 87.5, "mip_node_count": 42,
        },
    )
    preview = terminal_preview(result, placement_limit=2)
    assert "Validation   : VALID" in preview
    assert "Algorithm role: exact_reference" in preview
    assert "C01" in preview
    assert "I0001" in preview and "I0002" in preview
    assert "I0003" not in preview
    assert "1 rows hidden" in preview
    assert "MIP gap      : 12.500%" in preview
    assert "Best bound   : 87.5" in preview
    assert "MIP nodes    : 42" in preview


def test_terminal_preview_explains_capacity_limit_failure() -> None:
    result = RunResult(
        solve=SolveResult("PRECHECK_FAILED", "capacity", None, None, OptimizeResult()),
        placements=[], validation=None,
        metadata={
            "status": "PRECHECK_FAILED",
            "failure_class": "CAPACITY_LIMIT_PROVEN",
            "level_id": "level_02",
            "algorithm_id": "extreme_point_ffd",
            "n_items": 300,
            "n_containers": 500,
            "container_count": 0,
            "objective_value": None,
            "algorithm_runtime_seconds": 0.01,
            "run_dir": "outputs/level_02/runs/example",
            "container_count_lower_bound": 12,
            "max_used_container_count": 10,
            "capacity_limit_required_payload_kg": 72_500,
            "capacity_limit_attainable_payload_kg": 61_000,
            "capacity_limit_required_volume_m3": 100,
            "capacity_limit_attainable_volume_m3": 120,
            "construction_termination_reason": "hard_precheck_failed",
        },
    )

    preview = terminal_preview(result)

    assert "Class        : CAPACITY_LIMIT_PROVEN" in preview
    assert "Giới hạn container chắc chắn không đủ" in preview
    assert "Lower bound container: 12" in preview
    assert "Giới hạn container: 10" in preview


def test_validate_cli_rejects_level_mismatch(root, tmp_path):
    import json
    from container_packing.cli import main

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "manifest.json").write_text(json.dumps({"level": "level_01"}), encoding="utf-8")
    assert main(["validate", "--level", "level_02", "--run-dir", str(run_dir)]) == 2
