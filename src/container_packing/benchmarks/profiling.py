"""Diagnostic profiling for an already validated Level 2 benchmark candidate."""

from __future__ import annotations

import ast
import cProfile
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import pstats
from statistics import median
from typing import Any, Callable

import pandas as pd

from ..data_loader import load_config, merge_config
from ..experiments.contracts import ExperimentRequest
from ..provenance import runtime_metadata, sha256_file
from ..reporting import write_json, write_text
from ..runtime.project import find_project_root
from ..runtime.run_context import create_benchmark_profile_directory
from .runner import execute_experiment_case
from .stratified_evidence import build_stratified_evidence, build_stratified_evidence_for_protocol


PROFILE_ALGORITHMS = (
    "extreme_point_best_fit", "extreme_point_ffd", "maximal_space_best_fit",
)
_STATIC_RANDOM_SCALES = {100, 300, 500}
_STATIC_STRESS_SELECTIONS = {"largest_volume", "heaviest", "payload_pressure"}


@dataclass(frozen=True)
class ProfileCase:
    case_id: str
    source_stratum: str
    item_count: int
    container_count: int
    item_selection_strategy: str
    item_selection_seed: int | None
    config_path: Path
    config_overrides: dict[str, Any]


@dataclass(frozen=True)
class BenchmarkProfileResult:
    run_id: str
    run_dir: Path
    status: str
    selected_case_count: int
    execution_count: int


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return {}
    if isinstance(value, str) and value.strip():
        parsed = ast.literal_eval(value)
        if isinstance(parsed, dict):
            return parsed
    return {}


def _optional_int(value: Any) -> int | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return int(value)


def _load_request_cases(run_dir: Path, stratum: str) -> dict[str, ProfileCase]:
    request_path = run_dir / "benchmark" / "request.json"
    payload = json.loads(request_path.read_text(encoding="utf-8"))
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list):
        raise ValueError(f"Run {run_dir} does not contain a resolved corpus case catalog")
    cases: dict[str, ProfileCase] = {}
    for raw in raw_cases:
        case_id = str(raw.get("case_id", ""))
        if not case_id or case_id in cases:
            raise ValueError(f"Invalid or duplicate profile source case: {case_id!r}")
        cases[case_id] = ProfileCase(
            case_id=case_id,
            source_stratum=stratum,
            item_count=int(raw["item_count"]),
            container_count=int(raw["container_count"]),
            item_selection_strategy=str(raw["item_selection_strategy"]),
            item_selection_seed=_optional_int(raw.get("item_selection_seed")),
            config_path=Path(str(raw["config_file"])).resolve(),
            config_overrides=dict(_mapping(raw.get("config_overrides"))),
        )
    return cases


def _quality_difference_order(results: pd.DataFrame) -> list[str]:
    valid = results[
        results["success"].fillna(False).astype(bool)
        & results["validation_valid"].fillna(False).astype(bool)
    ].copy()
    records: list[tuple[float, float, int, str]] = []
    for case_id, group in valid.groupby("case_id", sort=True):
        objective = group.groupby("algorithm", sort=True).agg(
            containers=("used_container_count", "median"),
            cost=("total_container_cost", "median"),
            item_count=("item_count", "first"),
        )
        if len(objective) < 2:
            continue
        container_delta = float(objective["containers"].max() - objective["containers"].min())
        cost_delta = float(objective["cost"].max() - objective["cost"].min())
        if container_delta <= 0 and cost_delta <= 0:
            continue
        records.append((
            container_delta, cost_delta, int(objective["item_count"].max()), str(case_id),
        ))
    records.sort(key=lambda value: (-value[0], -value[1], -value[2], value[3]))
    return [value[3] for value in records]


def select_profile_cases(
    random_run_dir: Path,
    stress_run_dir: Path,
    prefix_run_dir: Path | None = None,
    *,
    maximum_difference_cases: int = 2,
) -> tuple[ProfileCase, ...]:
    """Select the fixed scale/stress anchors plus bounded objective differences."""
    random_cases = _load_request_cases(random_run_dir, "random_distribution")
    stress_cases = _load_request_cases(stress_run_dir, "stress")
    selected: list[ProfileCase] = sorted(
        (
            case for case in random_cases.values()
            if case.item_count in _STATIC_RANDOM_SCALES
            and case.item_selection_strategy == "stable_random"
            and case.item_selection_seed == 101
        ),
        key=lambda case: case.item_count,
    )
    stress_anchors = sorted(
        (
            case for case in stress_cases.values()
            if case.item_count == 500
            and case.item_selection_strategy in _STATIC_STRESS_SELECTIONS
        ),
        key=lambda case: case.item_selection_strategy,
    )
    selected.extend(stress_anchors)
    if len(selected) != 6:
        raise ValueError(
            "Profile source must provide random seed 101 at 100/300/500 items and "
            "all three 500-item stress policies"
        )
    selected_ids = {case.case_id for case in selected}
    source_cases = {**random_cases, **stress_cases}
    result_frames = [
        pd.read_csv(random_run_dir / "benchmark" / "results.csv"),
        pd.read_csv(stress_run_dir / "benchmark" / "results.csv"),
    ]
    if prefix_run_dir is not None:
        prefix_cases = _load_request_cases(prefix_run_dir, "prefix_regression")
        duplicate_ids = set(source_cases).intersection(prefix_cases)
        if duplicate_ids:
            raise ValueError(
                f"Profile source strata contain duplicate case IDs: {sorted(duplicate_ids)}"
            )
        source_cases.update(prefix_cases)
        result_frames.append(pd.read_csv(prefix_run_dir / "benchmark" / "results.csv"))
    difference_results = pd.concat(
        [frame for frame in result_frames if not frame.empty], ignore_index=True,
    )
    additions = 0
    for case_id in _quality_difference_order(difference_results):
        if case_id in selected_ids:
            continue
        selected.append(source_cases[case_id])
        selected_ids.add(case_id)
        additions += 1
        if additions >= maximum_difference_cases:
            break
    return tuple(selected)


def build_phase_profile(
    results: pd.DataFrame, selected_case_ids: set[str],
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    selected = results[results["case_id"].astype(str).isin(selected_case_ids)]
    for row in selected.to_dict(orient="records"):
        pipeline = _mapping(row.get("pipeline_phase_runtime_seconds"))
        inventory = _mapping(row.get("inventory_search_phase_runtime_seconds"))
        wall = float(row.get("wall_runtime_seconds") or 0.0)
        algorithm = float(pipeline.get("algorithm", row.get("algorithm_runtime_seconds") or 0.0))
        reporting = float(row.get("reporting_runtime_seconds") or 0.0)
        inventory_total = float(inventory.get("total_search", 0.0))
        normalization = float(inventory.get("normalization", 0.0))
        hard_precheck = float(inventory.get("hard_precheck", 0.0))
        lower_bound_and_capacity = float(inventory.get("lower_bound", 0.0)) + float(
            inventory.get("capacity_limit", 0.0)
        )
        improvement = float(inventory.get("incumbent_improvement", 0.0))
        if inventory_total > 0:
            # Existing telemetry measures `construction` from construction start until
            # consolidation returns, so remove the nested improvement timer here.
            construction = max(
                0.0,
                min(
                    float(inventory.get("construction", 0.0)) - improvement,
                    inventory_total
                    - normalization
                    - hard_precheck
                    - lower_bound_and_capacity
                    - improvement,
                ),
            )
            algorithm_other = max(
                0.0,
                algorithm
                - normalization
                - hard_precheck
                - lower_bound_and_capacity
                - construction
                - improvement,
            )
        else:
            construction = algorithm
            algorithm_other = 0.0
        phase_values = {
            "data_preparation": float(pipeline.get("data_preparation", 0.0)),
            "normalization": normalization,
            "hard_precheck": hard_precheck,
            "lower_bound_and_capacity": lower_bound_and_capacity,
            "construction": construction,
            "incumbent_improvement": improvement,
            "algorithm_other": algorithm_other,
            "independent_validation": float(pipeline.get("independent_validation", 0.0)),
            "reporting": reporting,
        }
        attributed = sum(phase_values.values())
        phase_values["unattributed"] = max(0.0, wall - attributed)
        for phase, seconds in phase_values.items():
            records.append({
                "case_id": str(row["case_id"]),
                "algorithm": str(row["algorithm"]),
                "item_count": int(row["item_count"]),
                "phase": phase,
                "seconds": seconds,
                "wall_runtime_seconds": wall,
                "candidate_feasibility_checks": row.get("candidate_feasibility_checks"),
                "extreme_points_evaluated": row.get("extreme_points_evaluated"),
                "peak_rss_bytes": row.get("peak_rss_bytes"),
            })
    frame = pd.DataFrame(records)
    if frame.empty:
        return frame
    grouped = frame.groupby(
        ["case_id", "algorithm", "item_count", "phase"], sort=True,
    ).agg(
        median_seconds=("seconds", "median"),
        min_seconds=("seconds", "min"),
        max_seconds=("seconds", "max"),
        median_wall_runtime_seconds=("wall_runtime_seconds", "median"),
        median_candidate_feasibility_checks=("candidate_feasibility_checks", "median"),
        median_extreme_points_evaluated=("extreme_points_evaluated", "median"),
        median_peak_rss_bytes=("peak_rss_bytes", "median"),
        sample_count=("seconds", "size"),
    ).reset_index()
    grouped["wall_time_share"] = grouped["median_seconds"] / grouped[
        "median_wall_runtime_seconds"
    ].where(grouped["median_wall_runtime_seconds"] > 0)
    return grouped


def _function_category(filename: str, function: str) -> str:
    value = f"{filename}/{function}".lower().replace("\\", "/")
    if any(token in value for token in ("reporting", "visualization", "plotly", "write_html")):
        return "reporting_visualization"
    if any(token in value for token in ("load_transfer", "load-bearing", "load_bearing")):
        return "load_transfer"
    if any(token in value for token in ("stackability", "stackable", "stack_group", "maximum_layer")):
        return "stackability"
    if any(token in value for token in ("exact_support", "support_ratio", "support_closure")):
        return "exact_support"
    if any(token in value for token in ("overlap", "placements_overlap")):
        return "overlap"
    if "support" in value:
        return "exact_support"
    if any(token in value for token in ("extreme_point", "maximal_space", "candidate")):
        return "candidate_enumeration"
    if "container_packing/algorithms" in value or "container_packing/levels" in value:
        return "other_solver"
    return "other_pipeline"


def _profile_rows(
    profile: cProfile.Profile, *, case_id: str, algorithm: str,
) -> list[dict[str, Any]]:
    stats = pstats.Stats(profile)
    records: list[dict[str, Any]] = []
    for (filename, line_number, function), values in stats.stats.items():
        primitive_calls, total_calls, self_time, cumulative_time, _ = values
        records.append({
            "case_id": case_id,
            "algorithm": algorithm,
            "filename": str(filename),
            "line_number": int(line_number),
            "function": str(function),
            "primitive_calls": int(primitive_calls),
            "total_calls": int(total_calls),
            "self_time_seconds": float(self_time),
            "cumulative_time_seconds": float(cumulative_time),
            "category": _function_category(str(filename), str(function)),
        })
    return sorted(records, key=lambda value: (-value["cumulative_time_seconds"], value["filename"], value["line_number"]))


def _decision_gate(phase_profile: pd.DataFrame, function_profile: pd.DataFrame) -> dict[str, Any]:
    shares = phase_profile.groupby("phase", sort=True)["wall_time_share"].median().to_dict()
    reporting_share = float(shares.get("reporting", 0.0))
    construction_share = float(shares.get("construction", 0.0))
    physical_categories = {"overlap", "exact_support", "stackability", "load_transfer"}
    solver_functions = function_profile[function_profile["category"].isin(
        physical_categories | {"candidate_enumeration", "other_solver"}
    )]
    category_times = solver_functions.groupby("category")["self_time_seconds"].sum().to_dict()
    solver_self_time = float(sum(category_times.values()))
    category_shares = {
        category: float(category_times.get(category, 0.0)) / max(solver_self_time, 1e-12)
        for category in sorted(physical_categories | {"candidate_enumeration"})
    }
    physical_share = sum(category_shares[category] for category in physical_categories)
    candidate_share = float(category_times.get("candidate_enumeration", 0.0)) / max(solver_self_time, 1e-12)
    priorities: list[str] = []
    if reporting_share >= 0.30:
        priorities.append("reporting_pipeline")
    if construction_share >= 0.30:
        if physical_share >= 0.40:
            priorities.append("spatial_or_contact_index")
        elif candidate_share >= 0.40:
            priorities.append("candidate_generation_and_pruning")
        else:
            priorities.append("construction_requires_deeper_measurement")
    if not priorities:
        priorities.append("no_runtime_optimization_gate_reached")
    return {
        "reporting_median_wall_share": reporting_share,
        "construction_median_wall_share": construction_share,
        "physical_constraint_share_of_profiled_solver_self_time": physical_share,
        "profiled_solver_category_shares": category_shares,
        # Compatibility for already-authored Level 2 report consumers.
        "support_overlap_share_of_profiled_solver_self_time": (
            category_shares["overlap"] + category_shares["exact_support"]
        ),
        "candidate_share_of_profiled_solver_self_time": candidate_share,
        "priorities": priorities,
        "note": (
            "cProfile is diagnostic and adds overhead; official runtime remains the "
            "unprofiled source benchmark telemetry."
        ),
    }


def run_benchmark_profile(
    *,
    level_id: str,
    random_run_dir: Path,
    stress_run_dir: Path,
    prefix_run_dir: Path,
    expected_protocol: dict[str, dict[str, Any]] | None = None,
    report_id: str | None = None,
    project_root: Path | None = None,
    executor: Callable[[ExperimentRequest, int], dict[str, Any]] = execute_experiment_case,
) -> BenchmarkProfileResult:
    """Profile a passed stratified benchmark without entering its ranking."""
    root = project_root.resolve() if project_root is not None else find_project_root()
    source_dirs = {
        "random_distribution": random_run_dir.resolve(),
        "stress": stress_run_dir.resolve(),
        "prefix_regression": prefix_run_dir.resolve(),
    }
    evidence = (
        build_stratified_evidence(source_dirs)
        if expected_protocol is None
        else build_stratified_evidence_for_protocol(
            source_dirs, level_id=level_id, expected=expected_protocol,
            report_id=report_id or f"{level_id}_stratified_benchmark_v2",
        )
    )
    if evidence["status"] != "PASS":
        raise ValueError(f"{level_id} profiling requires a PASS stratified evidence gate")
    cases = select_profile_cases(
        source_dirs["random_distribution"],
        source_dirs["stress"],
        source_dirs["prefix_regression"],
    )
    output_roots = {
        Path(merge_config(load_config(case.config_path), case.config_overrides)["paths"].get(
            "output_root", "outputs",
        ))
        for case in cases
    }
    if len(output_roots) != 1:
        raise ValueError("Every selected profile case must use the same output root")
    configured_root = next(iter(output_roots))
    output_root = configured_root if configured_root.is_absolute() else root / configured_root
    run_id, run_dir = create_benchmark_profile_directory(output_root, level_id, 42)
    profiles_dir = run_dir / "profiles"
    reports_dir = run_dir / "reports"
    profiles_dir.mkdir(parents=True)
    reports_dir.mkdir()

    random_results = pd.read_csv(source_dirs["random_distribution"] / "benchmark" / "results.csv")
    stress_results = pd.read_csv(source_dirs["stress"] / "benchmark" / "results.csv")
    prefix_results = pd.read_csv(
        source_dirs["prefix_regression"] / "benchmark" / "results.csv"
    )
    source_frames = [
        frame for frame in (random_results, stress_results, prefix_results)
        if not frame.empty
    ]
    if not source_frames:
        raise ValueError("Profile source runs do not contain benchmark results")
    normal_results = pd.concat(source_frames, ignore_index=True)
    selected_ids = {case.case_id for case in cases}
    phase_profile = build_phase_profile(normal_results, selected_ids)
    profile_results: list[dict[str, Any]] = []
    function_rows: list[dict[str, Any]] = []
    source_runs: list[str] = []
    mismatch_errors: list[str] = []
    for case in cases:
        baseline_case = normal_results[normal_results["case_id"].astype(str).eq(case.case_id)]
        for algorithm in PROFILE_ALGORITHMS:
            # cProfile adds enough overhead to trip the production wall-clock
            # deadline on otherwise complete candidates. Neutralize only that
            # deadline for diagnostic executions; bounded candidate/operator
            # guards remain unchanged and the result must still match the
            # unprofiled benchmark exactly.
            profiling_overrides = merge_config(
                case.config_overrides,
                {"container_search": {"time_limit_seconds": None}},
            )
            request = ExperimentRequest(
                level_id=level_id, algorithm_id=algorithm,
                config_path=case.config_path, item_count=case.item_count,
                container_count=case.container_count, environment="local",
                random_seed=42,
                item_selection_strategy=case.item_selection_strategy,
                item_selection_seed=case.item_selection_seed,
                config_overrides=profiling_overrides,
            )
            profiler = cProfile.Profile()
            profiler.enable()
            row = executor(request, 1)
            profiler.disable()
            profile_path = profiles_dir / f"{case.case_id}__{algorithm}.pstats"
            profiler.dump_stats(str(profile_path))
            row.update({
                "case_id": case.case_id,
                "benchmark_stratum": case.source_stratum,
                "diagnostic_profile": True,
                "pstats_file": str(profile_path.relative_to(run_dir)),
            })
            profile_results.append(row)
            function_rows.extend(_profile_rows(
                profiler, case_id=case.case_id, algorithm=algorithm,
            ))
            if row.get("experiment_run_dir"):
                source_runs.append(str(row["experiment_run_dir"]))
            expected = baseline_case[baseline_case["algorithm"].astype(str).eq(algorithm)]
            if expected.empty:
                mismatch_errors.append(f"{case.case_id}/{algorithm}: missing normal baseline")
                continue
            checks = {
                "success": bool(row.get("success")),
                "validation": bool(row.get("validation_valid")),
                "items": str(row.get("selected_item_ids_checksum")) in set(
                    expected["selected_item_ids_checksum"].astype(str)
                ),
                "objective": (
                    float(row.get("used_container_count")) in set(expected["used_container_count"].astype(float))
                    and float(row.get("total_container_cost")) in set(expected["total_container_cost"].astype(float))
                ) if row.get("used_container_count") is not None else False,
                "placement": str(row.get("placement_signature")) in set(
                    expected["placement_signature"].astype(str)
                ),
            }
            if not all(checks.values()):
                mismatch_errors.append(f"{case.case_id}/{algorithm}: {checks}")

    profile_frame = pd.DataFrame(profile_results)
    function_profile = pd.DataFrame(function_rows)
    decision = _decision_gate(phase_profile, function_profile)
    phase_profile.to_csv(run_dir / "phase_profile.csv", index=False, encoding="utf-8")
    function_profile.to_csv(run_dir / "function_profile.csv", index=False, encoding="utf-8")
    profile_frame.to_csv(run_dir / "profile_results.csv", index=False, encoding="utf-8")
    write_json(run_dir / "decision_gate.json", decision)
    status = "PASS" if not mismatch_errors else "FAIL"
    manifest = {
        "schema_version": "1.0",
        "project": "3d-container-packing",
        "run_type": "benchmark_profile",
        "level": level_id,
        "run_id": run_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "diagnostic_only": True,
        "deadline_neutralized_for_profiler_overhead": True,
        "eligible_for_benchmark_ranking": False,
        "selected_case_count": len(cases),
        "execution_count": len(profile_frame),
        "source_benchmark_runs": {key: str(value) for key, value in source_dirs.items()},
        "source_artifact_checksums": {
            str((run_dir_source / "benchmark" / filename).resolve()): sha256_file(
                run_dir_source / "benchmark" / filename
            )
            for run_dir_source in source_dirs.values()
            for filename in ("request.json", "results.csv")
        },
        "source_experiment_runs": source_runs,
        "selected_cases": [case.case_id for case in cases],
        "selected_case_requests": [
            {
                "case_id": case.case_id,
                "source_stratum": case.source_stratum,
                "item_count": case.item_count,
                "container_count": case.container_count,
                "item_selection_strategy": case.item_selection_strategy,
                "item_selection_seed": case.item_selection_seed,
                "config_file": str(case.config_path),
                "config_overrides": case.config_overrides,
                "profiling_config_overrides": merge_config(
                    case.config_overrides,
                    {"container_search": {"time_limit_seconds": None}},
                ),
            }
            for case in cases
        ],
        "algorithms": list(PROFILE_ALGORITHMS),
        "mismatch_errors": mismatch_errors,
        "artifacts": {
            "diagnostic": [
                "profile_manifest.json", "phase_profile.csv", "function_profile.csv",
                "profile_results.csv", "decision_gate.json", "reports/summary.md",
            ],
            "profiles": [str(path.relative_to(run_dir)) for path in sorted(profiles_dir.glob("*.pstats"))],
        },
        **runtime_metadata(root),
    }
    write_json(run_dir / "manifest.json", manifest)
    write_json(run_dir / "profile_manifest.json", manifest)
    priorities = ", ".join(decision["priorities"])
    write_text(reports_dir / "summary.md", (
        f"# Profiling diagnostic {level_id}\n\n"
        f"- Trạng thái: **{status}**.\n"
        f"- Số bài được chọn: {len(cases)}.\n"
        f"- Số lượt profiling: {len(profile_frame)}.\n"
        "- Runtime chính thức vẫn lấy từ benchmark V2 không bật profiler.\n"
        f"- Ưu tiên do decision gate đề xuất: `{priorities}`.\n\n"
        "Artifact này không tham gia objective, ranking hoặc WIN/TIE/LOSS.\n"
    ))
    return BenchmarkProfileResult(run_id, run_dir, status, len(cases), len(profile_frame))


def run_level2_benchmark_profile(**kwargs: Any) -> BenchmarkProfileResult:
    """Backward-compatible Level 2 entry point."""
    return run_benchmark_profile(level_id="level_02", **kwargs)
