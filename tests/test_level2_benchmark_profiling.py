import json
from pathlib import Path

import pandas as pd
import pytest

from container_packing.application.service import discover_benchmark_runs
from container_packing.benchmarks.profiling import (
    _function_category,
    build_phase_profile,
    ProfileCase,
    run_level2_benchmark_profile,
    select_profile_cases,
)
from container_packing.benchmarks.runner import execute_experiment_case
from container_packing.experiments.contracts import ExperimentRequest


ALGORITHMS = (
    "extreme_point_best_fit", "extreme_point_ffd", "maximal_space_best_fit",
)


@pytest.mark.parametrize(("filename", "function", "expected"), (
    ("algorithms/load_transfer.py", "propagate_load", "load_transfer"),
    ("algorithms/stackability.py", "check_stack_group", "stackability"),
    ("algorithms/exact_support.py", "support_ratio", "exact_support"),
    ("geometry.py", "placements_overlap", "overlap"),
    ("algorithms/extreme_point.py", "enumerate_candidates", "candidate_enumeration"),
    ("reporting/json_report.py", "write_report", "reporting_visualization"),
))
def test_profile_function_category_is_constraint_specific(
    filename: str, function: str, expected: str,
) -> None:
    assert _function_category(filename, function) == expected


def _case(
    root: Path, case_id: str, item_count: int, strategy: str,
    selection_seed: int | None,
) -> dict:
    return {
        "case_id": case_id, "item_count": item_count, "container_count": 1,
        "item_selection_strategy": strategy,
        "item_selection_seed": selection_seed,
        "config_file": str(root / "config/level_02/default.yaml"),
        "config_overrides": {},
    }


def _write_profile_source(run_dir: Path, cases: list[dict], results: list[dict]) -> None:
    benchmark = run_dir / "benchmark"
    benchmark.mkdir(parents=True)
    (benchmark / "request.json").write_text(
        json.dumps({"cases": cases}), encoding="utf-8",
    )
    pd.DataFrame(results).to_csv(benchmark / "results.csv", index=False)


def test_profile_case_selection_is_deterministic_and_bounded(
    root: Path, tmp_path: Path,
) -> None:
    random_cases = [
        _case(root, f"random_s101_i{count}", count, "stable_random", 101)
        for count in (100, 300, 500)
    ] + [
        _case(root, "difference_large", 500, "stable_random", 211),
        _case(root, "difference_cost", 300, "stable_random", 307),
        _case(root, "same_result", 200, "stable_random", 401),
    ]
    random_results: list[dict] = []
    for case in random_cases:
        counts = {
            "difference_large": (10, 12, 11),
            "difference_cost": (8, 8, 8),
        }.get(case["case_id"], (5, 5, 5))
        costs = (1000, 1200, 1100) if case["case_id"] == "difference_cost" else (1000, 1000, 1000)
        for algorithm, count, cost in zip(ALGORITHMS, counts, costs, strict=True):
            random_results.append({
                "case_id": case["case_id"], "algorithm": algorithm,
                "item_count": case["item_count"], "success": True,
                "validation_valid": True, "used_container_count": count,
                "total_container_cost": cost,
            })
    stress_cases = [
        _case(root, f"stress_{strategy}_i500", 500, strategy, None)
        for strategy in ("largest_volume", "heaviest", "payload_pressure")
    ]
    stress_results = [
        {
            "case_id": case["case_id"], "algorithm": algorithm,
            "item_count": 500, "success": True, "validation_valid": True,
            "used_container_count": 5, "total_container_cost": 1000,
        }
        for case in stress_cases
        for algorithm in ALGORITHMS
    ]
    prefix_cases = [_case(root, "prefix_difference", 500, "prefix", None)]
    prefix_results = [
        {
            "case_id": "prefix_difference", "algorithm": algorithm,
            "item_count": 500, "success": True, "validation_valid": True,
            "used_container_count": count, "total_container_cost": 1000,
        }
        for algorithm, count in zip(ALGORITHMS, (10, 14, 12), strict=True)
    ]
    _write_profile_source(tmp_path / "random", random_cases, random_results)
    _write_profile_source(tmp_path / "stress", stress_cases, stress_results)
    _write_profile_source(tmp_path / "prefix", prefix_cases, prefix_results)

    selected = select_profile_cases(
        tmp_path / "random", tmp_path / "stress", tmp_path / "prefix",
    )

    assert [case.case_id for case in selected[:3]] == [
        "random_s101_i100", "random_s101_i300", "random_s101_i500",
    ]
    assert {case.item_selection_strategy for case in selected[3:6]} == {
        "largest_volume", "heaviest", "payload_pressure",
    }
    assert [case.case_id for case in selected[6:]] == [
        "prefix_difference", "difference_large",
    ]
    assert len({case.case_id for case in selected}) == 8


def test_phase_profile_does_not_double_count_wall_runtime() -> None:
    source = pd.DataFrame([{
        "case_id": "case", "algorithm": "extreme_point_best_fit", "item_count": 500,
        "wall_runtime_seconds": 10.0, "reporting_runtime_seconds": 4.0,
        "pipeline_phase_runtime_seconds": {
            "data_preparation": 1.0, "algorithm": 4.0,
            "independent_validation": 1.0,
        },
        "inventory_search_phase_runtime_seconds": {
            "normalization": 0.1, "hard_precheck": 0.5, "lower_bound": 0.1,
            "capacity_limit": 0.1, "construction": 3.2,
            "incumbent_improvement": 1.0, "total_search": 4.0,
        },
        "candidate_feasibility_checks": 100, "extreme_points_evaluated": 100,
        "peak_rss_bytes": 1000,
    }])

    profile = build_phase_profile(source, {"case"})

    assert profile.groupby(["case_id", "algorithm"])["median_seconds"].sum().iloc[0] == pytest.approx(10.0)
    assert profile["wall_time_share"].sum() == pytest.approx(1.0)
    phase_seconds = profile.set_index("phase")["median_seconds"]
    assert phase_seconds["construction"] == pytest.approx(2.2)
    assert phase_seconds["incumbent_improvement"] == pytest.approx(1.0)


def test_profile_run_is_diagnostic_and_preserves_solution(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_root = tmp_path / "outputs"
    profile_case = ProfileCase(
        case_id="profile_i1", source_stratum="random_distribution",
        item_count=1, container_count=1, item_selection_strategy="prefix",
        item_selection_seed=None,
        config_path=root / "config/level_02/default.yaml",
        config_overrides={"paths": {"output_root": str(output_root)}},
    )
    baseline_rows = []
    for algorithm in ALGORITHMS[:2]:
        row = execute_experiment_case(ExperimentRequest(
            level_id="level_02", algorithm_id=algorithm,
            config_path=profile_case.config_path, item_count=1, container_count=1,
            random_seed=42, item_selection_strategy="prefix",
            config_overrides=profile_case.config_overrides,
        ), 1)
        row["case_id"] = profile_case.case_id
        baseline_rows.append(row)
    random_dir = tmp_path / "random"
    stress_dir = tmp_path / "stress"
    prefix_dir = tmp_path / "prefix"
    for directory, rows in (
        (random_dir, baseline_rows), (stress_dir, baseline_rows[:0]),
        (prefix_dir, baseline_rows[:0]),
    ):
        (directory / "benchmark").mkdir(parents=True)
        (directory / "benchmark/request.json").write_text(
            json.dumps({"cases": []}), encoding="utf-8",
        )
        pd.DataFrame(rows, columns=pd.DataFrame(baseline_rows).columns).to_csv(
            directory / "benchmark/results.csv", index=False,
        )
    monkeypatch.setattr(
        "container_packing.benchmarks.profiling.build_stratified_evidence",
        lambda _runs: {"status": "PASS"},
    )
    monkeypatch.setattr(
        "container_packing.benchmarks.profiling.select_profile_cases",
        lambda *_args, **_kwargs: (profile_case,),
    )
    monkeypatch.setattr(
        "container_packing.benchmarks.profiling.PROFILE_ALGORITHMS",
        ALGORITHMS[:2],
    )

    result = run_level2_benchmark_profile(
        random_run_dir=random_dir, stress_run_dir=stress_dir,
        prefix_run_dir=prefix_dir, project_root=root,
    )

    assert result.status == "PASS"
    assert result.selected_case_count == 1
    assert result.execution_count == 2
    manifest = json.loads((result.run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_type"] == "benchmark_profile"
    assert manifest["diagnostic_only"] is True
    assert manifest["deadline_neutralized_for_profiler_overhead"] is True
    assert manifest["eligible_for_benchmark_ranking"] is False
    assert manifest["selected_case_requests"][0]["item_count"] == 1
    assert manifest["selected_case_requests"][0]["profiling_config_overrides"][
        "container_search"
    ]["time_limit_seconds"] is None
    assert len(manifest["source_artifact_checksums"]) == 6
    assert (result.run_dir / "phase_profile.csv").is_file()
    assert (result.run_dir / "function_profile.csv").is_file()
    assert len(list((result.run_dir / "profiles").glob("*.pstats"))) == 2
    assert discover_benchmark_runs("level_02", root=tmp_path) == ()
