"""Run a reproducible experiment matrix and aggregate comparable metrics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Sequence

import pandas as pd
import yaml

from ..algorithms.registry import get_algorithm
from ..data_loader import load_config
from ..experiments.contracts import ExperimentRequest
from ..experiments.runner import run_experiment
from ..levels.registry import get_level
from ..metrics import packing_tiebreak_metrics, placement_signature
from ..provenance import runtime_metadata, sha256_file
from ..reporting import OUTPUT_SCHEMA_VERSION, write_json, write_text
from ..runtime.project import find_project_root
from ..runtime.run_context import create_benchmark_directory
from ..runtime.structured_logging import append_event
from .suites import BenchmarkScenario


@dataclass(frozen=True)
class BenchmarkResult:
    benchmark_id: str
    run_dir: Path
    results: pd.DataFrame
    summary: pd.DataFrame

    @property
    def successful(self) -> bool:
        return bool(len(self.results)) and bool(self.results["success"].all())


def _positive_values(values: Sequence[int], name: str) -> tuple[int, ...]:
    parsed = tuple(int(value) for value in values)
    if not parsed or any(value <= 0 for value in parsed):
        raise ValueError(f"{name} must contain one or more positive integers")
    return parsed


def _seed_values(values: Sequence[int]) -> tuple[int, ...]:
    parsed = tuple(int(value) for value in values)
    if not parsed:
        raise ValueError("seeds must contain one or more integers")
    if any(value < 0 for value in parsed):
        raise ValueError("seeds must be zero or greater")
    if len(set(parsed)) != len(parsed):
        raise ValueError("seeds must not contain duplicates; use repeats for repeated timing runs")
    return parsed


def _resolve(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _default_scenarios(item_counts: Sequence[int], container_counts: Sequence[int]) -> tuple[BenchmarkScenario, ...]:
    return tuple(
        BenchmarkScenario(
            scenario_id=f"items_{item_count}__containers_{container_count}",
            description=f"{item_count} items, {container_count} containers",
            item_count=item_count,
            container_count=container_count,
            tags=("ad_hoc",),
        )
        for item_count in item_counts
        for container_count in container_counts
    )


def _input_fingerprint(
    *,
    level_id: str,
    scenario: BenchmarkScenario,
    config: dict[str, Any],
    root: Path,
) -> str:
    """Hash the input and Level-1 contract shared by algorithms in one scenario."""
    raw_items = _resolve(root, config["paths"]["raw_items_csv"])
    payload = {
        "level": level_id,
        "scenario_id": scenario.scenario_id,
        "item_count": scenario.item_count,
        "container_count": scenario.container_count,
        "raw_items_checksum": sha256_file(raw_items),
        "containers": config.get("containers", []),
        "model": config.get("model", {}),
    }
    import hashlib
    import json

    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def execute_experiment_case(request: ExperimentRequest, repeat_index: int) -> dict[str, Any]:
    """Run one independently validated experiment and return a flat result row."""
    started = perf_counter()
    error: str | None = None
    signature: str | None = None
    bounding_volume: float | None = None
    coordinate_compactness: float | None = None
    try:
        result = run_experiment(request)
        metadata = result.metadata
        validation_valid = bool(result.validation and result.validation.valid)
        status = str(metadata["status"])
        success = status in {"OPTIMAL", "FEASIBLE", "FEASIBLE_TIME_LIMIT"} and validation_valid
        if result.placements:
            signature = placement_signature(result.placements)
            bounding_volume, coordinate_compactness = packing_tiebreak_metrics(result.placements)
    except Exception as exc:  # aggregate runners retain failed cells and continue
        metadata = {}
        validation_valid = False
        status = "ERROR"
        success = False
        error = f"{type(exc).__name__}: {exc}"
    return {
        "level": request.level_id,
        "algorithm": request.algorithm_id,
        "item_count": request.item_count,
        "container_count": request.container_count,
        "random_seed": request.random_seed,
        "repeat": repeat_index,
        "status": status,
        "validation_valid": validation_valid,
        "success": success,
        "objective_value": metadata.get("objective_value"),
        "used_container_count": metadata.get("container_count"),
        "total_container_cost": metadata.get("total_container_cost"),
        "occupied_bounding_volume_mm3": bounding_volume,
        "coordinate_compactness_mm": coordinate_compactness,
        "placement_signature": signature,
        "algorithm_runtime_seconds": metadata.get("algorithm_runtime_seconds"),
        "wall_runtime_seconds": perf_counter() - started,
        "experiment_run_id": metadata.get("run_id"),
        "experiment_run_dir": metadata.get("run_dir"),
        "error": error,
    }


def aggregate_results(frame: pd.DataFrame, *, extra_group_keys: Sequence[str] = ()) -> pd.DataFrame:
    """Aggregate runtime over repeats and quality over one value per seed."""
    keys = ["level", "algorithm", "item_count", "container_count", *extra_group_keys]
    grouped = frame.groupby(keys, sort=True, dropna=False)
    execution = grouped.agg(
        run_count=("success", "size"),
        seed_count=("random_seed", "nunique"),
        repeats_per_seed=("repeat", "nunique"),
        success_count=("success", "sum"),
        optimal_count=("status", lambda values: int((values == "OPTIMAL").sum())),
        algorithm_runtime_mean_seconds=("algorithm_runtime_seconds", "mean"),
        algorithm_runtime_std_seconds=("algorithm_runtime_seconds", "std"),
        wall_runtime_mean_seconds=("wall_runtime_seconds", "mean"),
        distinct_solution_count=("placement_signature", "nunique"),
    )
    per_seed = frame.groupby([*keys, "random_seed"], sort=True, dropna=False).agg(
        objective_value=("objective_value", "mean"),
        used_container_count=("used_container_count", "mean"),
        total_container_cost=("total_container_cost", "mean"),
        occupied_bounding_volume_mm3=("occupied_bounding_volume_mm3", "mean"),
        coordinate_compactness_mm=("coordinate_compactness_mm", "mean"),
    )
    quality = per_seed.groupby(keys, sort=True, dropna=False).agg(
        objective_mean=("objective_value", "mean"),
        objective_std=("objective_value", "std"),
        objective_min=("objective_value", "min"),
        objective_max=("objective_value", "max"),
        used_containers_mean=("used_container_count", "mean"),
        used_containers_std=("used_container_count", "std"),
        used_containers_min=("used_container_count", "min"),
        used_containers_max=("used_container_count", "max"),
        total_cost_mean=("total_container_cost", "mean"),
        total_cost_std=("total_container_cost", "std"),
        total_cost_min=("total_container_cost", "min"),
        total_cost_max=("total_container_cost", "max"),
        occupied_bounding_volume_mean_mm3=("occupied_bounding_volume_mm3", "mean"),
        occupied_bounding_volume_std_mm3=("occupied_bounding_volume_mm3", "std"),
        coordinate_compactness_mean_mm=("coordinate_compactness_mm", "mean"),
        coordinate_compactness_std_mm=("coordinate_compactness_mm", "std"),
    )
    summary = execution.join(quality).reset_index()
    summary["success_rate"] = summary["success_count"] / summary["run_count"]
    return summary.fillna({
        "algorithm_runtime_std_seconds": 0.0,
        "objective_std": 0.0,
        "used_containers_std": 0.0,
        "total_cost_std": 0.0,
        "occupied_bounding_volume_std_mm3": 0.0,
        "coordinate_compactness_std_mm": 0.0,
    })


def _aggregate(frame: pd.DataFrame) -> pd.DataFrame:
    """Backward-compatible default benchmark aggregation."""
    return aggregate_results(frame)


def run_benchmark(
    *,
    level_id: str,
    algorithm_ids: Sequence[str],
    item_counts: Sequence[int],
    container_counts: Sequence[int],
    repeats: int = 1,
    seeds: Sequence[int] | None = None,
    config_path: str | Path | None = None,
    environment: str = "local",
    project_root: str | Path | None = None,
    scenarios: Sequence[BenchmarkScenario] | None = None,
    suite_id: str | None = None,
    suite_source_path: str | Path | None = None,
) -> BenchmarkResult:
    """Execute all requested combinations and retain failures as benchmark rows."""
    if repeats <= 0:
        raise ValueError("repeats must be a positive integer")
    items = _positive_values(item_counts, "item_counts")
    containers = _positive_values(container_counts, "container_counts")
    selected_scenarios = tuple(scenarios) if scenarios is not None else _default_scenarios(items, containers)
    if not selected_scenarios:
        raise ValueError("scenarios must not be empty")
    if len({value.scenario_id for value in selected_scenarios}) != len(selected_scenarios):
        raise ValueError("scenarios must have unique scenario_id values")
    for scenario in selected_scenarios:
        _positive_values((scenario.item_count,), f"scenario {scenario.scenario_id}.item_count")
        _positive_values((scenario.container_count,), f"scenario {scenario.scenario_id}.container_count")
    level = get_level(level_id)
    algorithms = tuple(str(value) for value in algorithm_ids)
    if not algorithms:
        raise ValueError("algorithm_ids must not be empty")
    for algorithm_id in algorithms:
        definition = get_algorithm(algorithm_id)
        if algorithm_id not in level.supported_algorithms or level_id not in definition.supported_levels:
            raise ValueError(f"{algorithm_id} is not compatible with {level_id}")

    root = Path(project_root).resolve() if project_root is not None else find_project_root()
    selected_config = Path(config_path) if config_path is not None else level.default_config
    config_file = _resolve(root, selected_config)
    config = load_config(config_file)
    output_root = _resolve(root, config["paths"].get("output_root", "outputs"))
    configured_seed = int(config.get("project", {}).get("random_seed", 42))
    random_seeds = _seed_values((configured_seed,) if seeds is None else seeds)
    benchmark_id, run_dir = create_benchmark_directory(output_root, level_id, random_seeds)
    benchmark_dir = run_dir / "benchmark"
    log_path = run_dir / "logs" / "run.log"
    benchmark_dir.mkdir(parents=True)
    log_path.parent.mkdir(parents=True)

    request_payload = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "level": level_id,
        "algorithms": list(algorithms),
        "item_counts": list(items),
        "container_counts": list(containers),
        "suite_id": suite_id,
        "suite_source_path": str(suite_source_path) if suite_source_path is not None else None,
        "scenarios": [
            {
                "scenario_id": value.scenario_id,
                "description": value.description,
                "item_count": value.item_count,
                "container_count": value.container_count,
                "tags": list(value.tags),
                "input_fingerprint": _input_fingerprint(level_id=level_id, scenario=value, config=config, root=root),
            }
            for value in selected_scenarios
        ],
        "repeats": repeats,
        "random_seeds": list(random_seeds),
        "environment": environment,
        "config_file": str(config_file),
    }
    write_json(benchmark_dir / "request.json", request_payload)
    resolved_config_path = run_dir / "resolved_config.yaml"
    config["benchmark"] = {"random_seeds": list(random_seeds), "repeats_per_seed": repeats}
    write_text(resolved_config_path, yaml.safe_dump(config, sort_keys=False))
    append_event(log_path, "benchmark_started", benchmark_id=benchmark_id, **request_payload)

    rows: list[dict[str, Any]] = []
    for algorithm_id in algorithms:
        for scenario in selected_scenarios:
            fingerprint = _input_fingerprint(level_id=level_id, scenario=scenario, config=config, root=root)
            for random_seed in random_seeds:
                for repeat_index in range(1, repeats + 1):
                    request = ExperimentRequest(
                        level_id=level_id, algorithm_id=algorithm_id, config_path=config_file,
                        item_count=scenario.item_count, container_count=scenario.container_count, environment=environment,
                        random_seed=random_seed,
                    )
                    row = {
                        "benchmark_id": benchmark_id,
                        "suite_id": suite_id or "ad_hoc",
                        "scenario_id": scenario.scenario_id,
                        "scenario_description": scenario.description,
                        "scenario_tags": ",".join(scenario.tags),
                        "input_fingerprint": fingerprint,
                        **execute_experiment_case(request, repeat_index),
                    }
                    rows.append(row)
                    append_event(log_path, "benchmark_case_completed", **row)

    results = pd.DataFrame(rows)
    summary = aggregate_results(
        results,
        extra_group_keys=("suite_id", "scenario_id", "scenario_description", "scenario_tags", "input_fingerprint"),
    )
    results.to_csv(benchmark_dir / "results.csv", index=False, encoding="utf-8")
    summary.to_csv(benchmark_dir / "summary.csv", index=False, encoding="utf-8")
    write_json(benchmark_dir / "summary.json", {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "rows": summary.to_dict(orient="records"),
    })
    succeeded = int(results["success"].sum())
    status = "SUCCESS" if succeeded == len(results) else ("PARTIAL" if succeeded else "FAILED")
    manifest = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "project": "3d-container-packing",
        "run_type": "benchmark",
        "level": level_id,
        "run_id": benchmark_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "environment": environment,
        "random_seed": random_seeds[0] if len(random_seeds) == 1 else None,
        "random_seeds": list(random_seeds),
        "repeats_per_seed": repeats,
        "suite_id": suite_id or "ad_hoc",
        "suite_source_path": str(suite_source_path) if suite_source_path is not None else None,
        "suite_source_checksum": sha256_file(suite_source_path) if suite_source_path is not None else None,
        "comparison_protocol": {
            "same_level_only": True,
            "same_scenario_for_all_algorithms": True,
            "shared_input_fingerprint": True,
            "quality_aggregated_across_seeds": True,
            "runtime_repeated_per_seed": True,
        },
        "status": status,
        "case_count": len(results),
        "successful_case_count": succeeded,
        "config_file": str(config_file),
        "resolved_config_checksum": sha256_file(resolved_config_path),
        "source_runs": [value for value in results["experiment_run_dir"].dropna().tolist()],
        "artifacts": {
            "canonical": ["manifest.json", "resolved_config.yaml", "benchmark/request.json", "benchmark/results.csv"],
            "derived": ["benchmark/summary.csv", "benchmark/summary.json", "reports/summary.md"],
            "diagnostics": ["logs/run.log"],
        },
        **runtime_metadata(root),
    }
    write_json(run_dir / "manifest.json", manifest)
    report_dir = run_dir / "reports"
    report_dir.mkdir()
    write_text(report_dir / "summary.md", (
        f"# Benchmark {benchmark_id}\n\n- Status: {status}\n- Cases: {len(results)}\n"
        f"- Successful: {succeeded}\n- Level: {level_id}\n- Algorithms: {', '.join(algorithms)}\n"
        f"- Seeds: {', '.join(str(value) for value in random_seeds)}\n- Repeats per seed: {repeats}\n"
    ))
    append_event(log_path, "benchmark_completed", benchmark_id=benchmark_id, status=status, cases=len(results), successful=succeeded)
    return BenchmarkResult(benchmark_id, run_dir, results, summary)
