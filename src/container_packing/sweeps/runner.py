"""Execute reproducible, independently validated parameter grids."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from itertools import product
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd
import yaml

from ..algorithms.registry import get_algorithm
from ..benchmarks.runner import aggregate_results, execute_experiment_case
from ..data_loader import load_config
from ..experiments.contracts import ExperimentRequest
from ..levels.registry import get_level
from ..provenance import runtime_metadata, sha256_file
from ..reporting import OUTPUT_SCHEMA_VERSION, write_json, write_text
from ..runtime.project import find_project_root
from ..runtime.run_context import create_parameter_sweep_directory
from ..runtime.structured_logging import append_event


@dataclass(frozen=True)
class ParameterSweepResult:
    sweep_id: str
    run_dir: Path
    parameter_sets: pd.DataFrame
    results: pd.DataFrame
    summary: pd.DataFrame
    ranking: pd.DataFrame

    @property
    def successful(self) -> bool:
        return bool(len(self.results)) and bool(self.results["success"].all())


def _positive(values: Sequence[int], name: str) -> tuple[int, ...]:
    parsed = tuple(int(value) for value in values)
    if not parsed or any(value <= 0 for value in parsed):
        raise ValueError(f"{name} must contain positive integers")
    return parsed


def _seeds(values: Sequence[int]) -> tuple[int, ...]:
    parsed = tuple(int(value) for value in values)
    if not parsed or any(value < 0 for value in parsed):
        raise ValueError("seeds must contain non-negative integers")
    if len(set(parsed)) != len(parsed):
        raise ValueError("seeds must not contain duplicates")
    return parsed


def _parameter_sets(
    grid: Mapping[str, Sequence[Any]], allowed: set[str], max_parameter_sets: int,
) -> list[tuple[str, dict[str, Any]]]:
    if not grid:
        raise ValueError("sweep.parameters must define at least one parameter")
    unknown = sorted(set(grid) - allowed)
    if unknown:
        raise ValueError(f"Unknown algorithm parameters: {', '.join(unknown)}")
    names = list(grid)
    value_lists: list[list[Any]] = []
    for name in names:
        if isinstance(grid[name], (str, bytes)) or not isinstance(grid[name], Sequence):
            raise ValueError(f"Parameter {name!r} values must be a YAML list")
        values = list(grid[name])
        if not values:
            raise ValueError(f"Parameter {name!r} must contain at least one value")
        signatures = [json.dumps(value, sort_keys=True) for value in values]
        if len(set(signatures)) != len(signatures):
            raise ValueError(f"Parameter {name!r} contains duplicate values")
        value_lists.append(values)
    count = 1
    for values in value_lists:
        count *= len(values)
    if count > max_parameter_sets:
        raise ValueError(f"Parameter grid creates {count} sets, above max_parameter_sets={max_parameter_sets}")
    sets: list[tuple[str, dict[str, Any]]] = []
    for index, values in enumerate(product(*value_lists), start=1):
        parameters = dict(zip(names, values, strict=True))
        canonical = json.dumps(parameters, sort_keys=True, separators=(",", ":"))
        fingerprint = sha256(canonical.encode("utf-8")).hexdigest()[:8]
        sets.append((f"p{index:03d}_{fingerprint}", parameters))
    return sets


def _ranking(summary: pd.DataFrame, parameter_columns: list[str]) -> pd.DataFrame:
    values = summary.copy()
    values["_failure_rate"] = 1.0 - values["success_rate"]
    group_keys = ["level", "algorithm", "item_count", "container_count"]
    sort_columns = [
        *group_keys, "_failure_rate", "used_containers_max", "used_containers_mean",
        "total_cost_max", "total_cost_mean", "total_cost_std",
        "objective_max", "objective_mean", "objective_std",
        "occupied_bounding_volume_mean_mm3", "occupied_bounding_volume_std_mm3",
        "coordinate_compactness_mean_mm", "coordinate_compactness_std_mm",
        "algorithm_runtime_mean_seconds", "parameter_set_id",
    ]
    values = values.sort_values(sort_columns, ascending=True, na_position="last").reset_index(drop=True)
    values["rank"] = values.groupby(group_keys, sort=False).cumcount() + 1
    values = values.drop(columns=["_failure_rate"])
    leading = [*group_keys, "rank", "parameter_set_id", *parameter_columns]
    return values[[*leading, *[column for column in values.columns if column not in leading]]]


def run_parameter_sweep(
    sweep_config_path: str | Path,
    *,
    seeds: Sequence[int] | None = None,
    repeats: int | None = None,
    item_counts: Sequence[int] | None = None,
    container_counts: Sequence[int] | None = None,
    project_root: str | Path | None = None,
) -> ParameterSweepResult:
    root = Path(project_root).resolve() if project_root is not None else find_project_root()
    definition_file = Path(sweep_config_path)
    definition_file = definition_file.resolve() if definition_file.is_absolute() else (root / definition_file).resolve()
    definition = load_config(definition_file)
    project = definition.get("project", {})
    level_id = str(project.get("level_id", ""))
    algorithm_id = str(project.get("algorithm_id", ""))
    level = get_level(level_id)
    algorithm = get_algorithm(algorithm_id)
    if algorithm_id not in level.supported_algorithms or level_id not in algorithm.supported_levels:
        raise ValueError(f"{algorithm_id!r} is not compatible with {level_id!r}")

    base_value = definition.get("base_config")
    if not base_value:
        raise ValueError("Parameter sweep must define base_config")
    base_file = Path(str(base_value))
    base_file = base_file.resolve() if base_file.is_absolute() else (root / base_file).resolve()
    base_config = load_config(base_file)
    section_name = "solver" if algorithm_id == "milp_big_m" else "algorithms"
    base_settings = (
        base_config.get("solver", {}) if algorithm_id == "milp_big_m"
        else base_config.get("algorithms", {}).get(algorithm_id, {})
    )
    if not isinstance(base_settings, dict) or not base_settings:
        raise ValueError(f"Base config has no settings for {algorithm_id!r} in {section_name}")

    instance = definition.get("instance", {})
    execution = definition.get("execution", {})
    resolved_items = _positive(instance.get("item_counts", []) if item_counts is None else item_counts, "item_counts")
    resolved_containers = _positive(
        instance.get("container_counts", []) if container_counts is None else container_counts,
        "container_counts",
    )
    resolved_seeds = _seeds(execution.get("seeds", []) if seeds is None else seeds)
    resolved_repeats = int(execution.get("repeats", 1) if repeats is None else repeats)
    if resolved_repeats <= 0:
        raise ValueError("repeats must be positive")
    environment = str(execution.get("environment", "local"))
    if environment not in {"local", "colab", "kaggle"}:
        raise ValueError(f"Unsupported environment {environment!r}")
    sweep = definition.get("sweep", {})
    parameter_values = _parameter_sets(
        sweep.get("parameters", {}), set(base_settings), int(sweep.get("max_parameter_sets", 100)),
    )

    output_value = Path(str(base_config.get("paths", {}).get("output_root", "outputs")))
    output_root = output_value.resolve() if output_value.is_absolute() else (root / output_value).resolve()
    sweep_id, run_dir = create_parameter_sweep_directory(output_root, level_id, algorithm_id, resolved_seeds)
    sweep_dir = run_dir / "sweep"
    log_path = run_dir / "logs" / "run.log"
    sweep_dir.mkdir(parents=True)
    log_path.parent.mkdir(parents=True)

    parameter_rows = [{"parameter_set_id": identifier, **values} for identifier, values in parameter_values]
    parameter_frame = pd.DataFrame(parameter_rows)
    request_payload = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "level": level_id, "algorithm": algorithm_id,
        "base_config": str(base_file), "sweep_config": str(definition_file),
        "item_counts": list(resolved_items), "container_counts": list(resolved_containers),
        "random_seeds": list(resolved_seeds), "repeats_per_seed": resolved_repeats,
        "environment": environment, "parameter_set_count": len(parameter_values),
        "case_count": len(parameter_values) * len(resolved_items) * len(resolved_containers) * len(resolved_seeds) * resolved_repeats,
        "parameters": sweep.get("parameters", {}),
    }
    write_json(sweep_dir / "request.json", request_payload)
    parameter_frame.to_csv(sweep_dir / "parameter_sets.csv", index=False, encoding="utf-8")
    resolved_config_path = run_dir / "resolved_config.yaml"
    write_text(resolved_config_path, yaml.safe_dump({
        "parameter_sweep": request_payload,
        "base_experiment_config": base_config,
    }, sort_keys=False))
    append_event(log_path, "parameter_sweep_started", sweep_id=sweep_id, **request_payload)

    rows: list[dict[str, Any]] = []
    for parameter_set_id, parameters in parameter_values:
        for item_count in resolved_items:
            for container_count in resolved_containers:
                for random_seed in resolved_seeds:
                    for repeat_index in range(1, resolved_repeats + 1):
                        request = ExperimentRequest(
                            level_id=level_id, algorithm_id=algorithm_id, config_path=base_file,
                            item_count=item_count, container_count=container_count,
                            environment=environment, random_seed=random_seed,
                            algorithm_parameters=parameters,
                        )
                        row = {
                            "sweep_id": sweep_id, "parameter_set_id": parameter_set_id,
                            **execute_experiment_case(request, repeat_index),
                        }
                        rows.append(row)
                        append_event(log_path, "parameter_sweep_case_completed", **row)

    results = pd.DataFrame(rows)
    summary = aggregate_results(results, extra_group_keys=("parameter_set_id",))
    parameter_columns = [column for column in parameter_frame.columns if column != "parameter_set_id"]
    summary = summary.merge(parameter_frame, on="parameter_set_id", how="left", validate="many_to_one")
    ranking = _ranking(summary, parameter_columns)
    results.to_csv(sweep_dir / "results.csv", index=False, encoding="utf-8")
    summary.to_csv(sweep_dir / "summary.csv", index=False, encoding="utf-8")
    ranking.to_csv(sweep_dir / "ranking.csv", index=False, encoding="utf-8")
    write_json(sweep_dir / "summary.json", {
        "schema_version": OUTPUT_SCHEMA_VERSION, "rows": summary.to_dict(orient="records"),
    })
    best = ranking[ranking["rank"] == 1]
    write_json(sweep_dir / "best_parameters.json", {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "selection_rule": [
            "success_rate_desc", "used_containers_max_asc", "used_containers_mean_asc",
            "total_cost_max_mean_std_asc", "objective_max_mean_std_asc",
            "occupied_bounding_volume_mean_std_mm3_asc",
            "coordinate_compactness_mean_std_mm_asc", "algorithm_runtime_mean_seconds_asc",
        ],
        "rows": best[["item_count", "container_count", "parameter_set_id", *parameter_columns]].to_dict(orient="records"),
    })

    succeeded = int(results["success"].sum())
    status = "SUCCESS" if succeeded == len(results) else ("PARTIAL" if succeeded else "FAILED")
    manifest = {
        "schema_version": OUTPUT_SCHEMA_VERSION, "project": "3d-container-packing",
        "run_type": "parameter_sweep", "level": level_id, "algorithm": algorithm_id,
        "run_id": sweep_id, "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "environment": environment, "random_seed": resolved_seeds[0] if len(resolved_seeds) == 1 else None,
        "random_seeds": list(resolved_seeds), "repeats_per_seed": resolved_repeats,
        "parameter_set_count": len(parameter_values), "case_count": len(results),
        "successful_case_count": succeeded, "status": status,
        "config_file": str(definition_file), "base_config_file": str(base_file),
        "resolved_config_checksum": sha256_file(resolved_config_path),
        "source_runs": [value for value in results["experiment_run_dir"].dropna().tolist()],
        "artifacts": {
            "canonical": ["manifest.json", "resolved_config.yaml", "sweep/request.json", "sweep/parameter_sets.csv", "sweep/results.csv"],
            "derived": ["sweep/summary.csv", "sweep/summary.json", "sweep/ranking.csv", "sweep/best_parameters.json", "reports/summary.md"],
            "diagnostics": ["logs/run.log"],
        },
        **runtime_metadata(root),
    }
    write_json(run_dir / "manifest.json", manifest)
    report_dir = run_dir / "reports"
    report_dir.mkdir()
    write_text(report_dir / "summary.md", (
        f"# Parameter sweep {sweep_id}\n\n- Status: {status}\n- Algorithm: {algorithm_id}\n"
        f"- Parameter sets: {len(parameter_values)}\n- Cases: {len(results)}\n- Successful: {succeeded}\n"
        f"- Seeds: {', '.join(str(value) for value in resolved_seeds)}\n"
    ))
    append_event(log_path, "parameter_sweep_completed", sweep_id=sweep_id, status=status, cases=len(results), successful=succeeded)
    return ParameterSweepResult(sweep_id, run_dir, parameter_frame, results, summary, ranking)
