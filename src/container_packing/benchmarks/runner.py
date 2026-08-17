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
from ..data_loader import load_config, merge_config
from ..dataset_usage import DatasetExecutionIntent, DatasetUsageEvidence, validate_dataset_usage
from ..experiments.contracts import ExperimentRequest
from ..experiments.runner import run_experiment
from ..instance_data import item_selection_fingerprint
from ..levels.registry import get_level
from ..metrics import packing_tiebreak_metrics, placement_signature
from ..provenance import runtime_metadata, sha256_file
from ..reporting import OUTPUT_SCHEMA_VERSION, write_json, write_text
from ..runtime.project import find_project_root
from ..runtime.performance import PeakMemorySampler
from ..runtime.run_context import create_benchmark_directory
from ..runtime.structured_logging import append_event
from .analysis import BenchmarkAnalysis, analyze_benchmark
from .distribution import (
    build_case_algorithm_summary,
    build_case_differences,
    build_case_features,
    build_distribution_summary,
    build_pairwise_outcomes,
)
from .fingerprint import (
    experiment_fingerprint,
    referenced_semantic_file_checksums,
    semantic_input_fingerprint,
)
from .suites import BenchmarkScenario


@dataclass(frozen=True)
class BenchmarkResult:
    benchmark_id: str
    run_dir: Path
    results: pd.DataFrame
    summary: pd.DataFrame
    analysis: BenchmarkAnalysis

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
    selection: dict[str, Any] | None = None,
    dataset_usage: DatasetUsageEvidence | None = None,
) -> str:
    """Hash the complete level contract shared by algorithms in one scenario."""
    raw_items = _resolve(root, config["paths"]["raw_items_csv"])
    selection = selection or item_selection_fingerprint(
        raw_items, scenario.item_count,
        strategy=scenario.item_selection_strategy, seed=scenario.item_selection_seed,
        mapping_path=(
            _resolve(root, config["paths"]["items_source_mapping"])
            if config["paths"].get("items_source_mapping") else None
        ),
    )
    return semantic_input_fingerprint(
        level_id=level_id,
        scenario=scenario,
        config=config,
        root=root,
        selection=selection,
        dataset_usage=dataset_usage,
    )


def execute_experiment_case(request: ExperimentRequest, repeat_index: int) -> dict[str, Any]:
    """Run one independently validated experiment and return a flat result row."""
    started = perf_counter()
    error: str | None = None
    signature: str | None = None
    bounding_volume: float | None = None
    coordinate_compactness: float | None = None
    peak_rss_bytes: int | None = None
    try:
        with PeakMemorySampler() as memory:
            result = run_experiment(request)
        peak_rss_bytes = memory.peak_rss_bytes
        metadata = result.metadata
        validation_valid = bool(result.validation and result.validation.valid)
        status = str(metadata["status"])
        success = status in {"OPTIMAL", "FEASIBLE", "FEASIBLE_TIME_LIMIT"} and validation_valid
        if not success and (
            metadata.get("objective_value") is not None
            or metadata.get("official_objective") is not None
            or metadata.get("official_secondary_search_score") is not None
            or metadata.get("diagnostic_secondary_search_score") is not None
        ):
            raise ValueError(
                "Benchmark invariant violated: failed/invalid run reported an objective"
            )
        if result.placements:
            signature = placement_signature(result.placements)
            bounding_volume, coordinate_compactness = packing_tiebreak_metrics(result.placements)
    except Exception as exc:  # aggregate runners retain failed cells and continue
        metadata = {}
        validation_valid = False
        status = "ERROR"
        success = False
        error = f"{type(exc).__name__}: {exc}"
    wall_runtime_seconds = perf_counter() - started
    secondary_score = metadata.get("official_secondary_search_score")
    if not isinstance(secondary_score, dict):
        secondary_score = {}
    diagnostic_score = metadata.get("diagnostic_secondary_search_score")
    if not isinstance(diagnostic_score, dict):
        diagnostic_score = {}
    pipeline_runtime_seconds = metadata.get("pipeline_runtime_seconds")
    reporting_runtime_seconds = None
    if isinstance(pipeline_runtime_seconds, int | float):
        reporting_runtime_seconds = max(
            0.0, wall_runtime_seconds - float(pipeline_runtime_seconds)
        )
    aggregate_lower_bound = next((
        metadata.get(key)
        for key in (
            "aggregate_lower_bound",
            "container_subset_aggregate_lower_bound",
            "capacity_limit_aggregate_lower_bound",
            "container_count_lower_bound",
        )
        if metadata.get(key) is not None
    ), None)
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
        "encoded_solver_objective": metadata.get("encoded_solver_objective"),
        "official_objective": metadata.get("official_objective"),
        "official_secondary_search_score": metadata.get(
            "official_secondary_search_score"
        ),
        "secondary_utilization_concentration": secondary_score.get(
            "utilization_concentration"
        ),
        "secondary_internal_void_ratio": secondary_score.get(
            "internal_void_ratio"
        ),
        "secondary_minimum_support_margin": secondary_score.get(
            "minimum_support_margin"
        ),
        "diagnostic_secondary_search_score": metadata.get(
            "diagnostic_secondary_search_score"
        ),
        "diagnostic_secondary_utilization_concentration": diagnostic_score.get(
            "utilization_concentration"
        ),
        "diagnostic_secondary_internal_void_ratio": diagnostic_score.get(
            "internal_void_ratio"
        ),
        "diagnostic_secondary_minimum_support_margin": diagnostic_score.get(
            "minimum_support_margin"
        ),
        "used_container_count": metadata.get("container_count"),
        "total_container_cost": metadata.get("total_container_cost"),
        "occupied_bounding_volume_mm3": bounding_volume,
        "coordinate_compactness_mm": coordinate_compactness,
        "placement_signature": signature,
        "algorithm_runtime_seconds": metadata.get("algorithm_runtime_seconds"),
        "wall_runtime_seconds": wall_runtime_seconds,
        "reporting_runtime_seconds": reporting_runtime_seconds,
        "peak_rss_bytes": peak_rss_bytes,
        "pipeline_phase_runtime_seconds": metadata.get(
            "pipeline_phase_runtime_seconds"
        ),
        "inventory_search_phase_runtime_seconds": metadata.get(
            "inventory_search_phase_runtime_seconds"
        ),
        "experiment_run_id": metadata.get("run_id"),
        "experiment_run_dir": metadata.get("run_dir"),
        "error": error,
        "instance_id": metadata.get("instance_id"),
        "selected_item_ids_checksum": metadata.get("selected_item_ids_checksum"),
        "feasibility_policy": metadata.get("feasibility_policy"),
        "support_threshold": metadata.get("support_threshold"),
        "minimum_exact_support_ratio": metadata.get("minimum_exact_support_ratio"),
        "orientation_profile": metadata.get("orientation_profile"),
        "orientation_candidates_evaluated": metadata.get("orientation_candidates_evaluated"),
        "candidate_feasibility_checks": metadata.get("candidate_feasibility_checks"),
        "geometry_rejected_candidates": metadata.get("geometry_rejected_candidates"),
        "support_rejected_candidates": metadata.get("support_rejected_candidates"),
        "stackability_rejected_candidates": metadata.get(
            "stackability_rejected_candidates"
        ),
        "load_bearing_rejected_candidates": metadata.get(
            "load_bearing_rejected_candidates"
        ),
        "extreme_points_evaluated": metadata.get("extreme_points_evaluated"),
        "candidate_subsets_evaluated": metadata.get("candidate_subsets_evaluated"),
        "contact_support_index_enabled": metadata.get(
            "contact_support_index_enabled"
        ),
        "contact_support_index_version": metadata.get(
            "contact_support_index_version"
        ),
        "contact_support_index_queries": metadata.get(
            "contact_support_index_queries"
        ),
        "contact_support_index_cache_hits": metadata.get(
            "contact_support_index_cache_hits"
        ),
        "contact_support_index_cache_misses": metadata.get(
            "contact_support_index_cache_misses"
        ),
        "contact_support_index_placements_examined": metadata.get(
            "contact_support_index_placements_examined"
        ),
        "contact_support_index_committed_placements": metadata.get(
            "contact_support_index_committed_placements"
        ),
        "contact_support_index_exact_contact_checks": metadata.get(
            "contact_support_index_exact_contact_checks"
        ),
        "contact_support_index_query_runtime_seconds": metadata.get(
            "contact_support_index_query_runtime_seconds"
        ),
        "contact_support_index_estimated_scans_avoided": metadata.get(
            "contact_support_index_estimated_scans_avoided"
        ),
        "aggregate_lower_bound": aggregate_lower_bound,
        "container_consolidation_candidates_evaluated": metadata.get(
            "container_consolidation_candidates_evaluated"
        ),
        "container_consolidation_attempted": metadata.get(
            "container_consolidation_attempted"
        ),
        "container_consolidation_initial_count": metadata.get(
            "container_consolidation_initial_count"
        ),
        "container_consolidation_final_count": metadata.get(
            "container_consolidation_final_count"
        ),
        "container_consolidation_runtime_seconds": metadata.get(
            "container_consolidation_runtime_seconds"
        ),
        "container_consolidation_termination_reason": metadata.get(
            "container_consolidation_termination_reason"
        ),
        "best_partial_placement_count": metadata.get(
            "best_partial_placement_count"
        ),
        "incumbent_acquisition_cardinality_ladder": metadata.get(
            "incumbent_acquisition_cardinality_ladder"
        ),
        "incumbent_acquisition_attempt_count": metadata.get(
            "incumbent_acquisition_attempt_count"
        ),
        "validated_incumbent_candidates_considered": metadata.get(
            "validated_incumbent_candidates_considered"
        ),
        "search_termination_reason": metadata.get(
            "inventory_search_termination_reason",
            metadata.get(
                "container_consolidation_termination_reason",
                metadata.get("construction_termination_reason"),
            ),
        ),
    }


def annotate_reference_gaps(
    frame: pd.DataFrame,
    *,
    instance_keys: Sequence[str] = ("level", "scenario_id", "input_fingerprint"),
) -> pd.DataFrame:
    """Gắn mốc exact/best-known mà không trộn các instance khác input."""
    if frame.empty:
        return frame.copy()
    keys = list(instance_keys)
    missing = [key for key in keys if key not in frame.columns]
    if missing:
        raise ValueError(f"Reference instance keys are missing from results: {missing}")

    references: list[dict[str, Any]] = []
    for group_values, group in frame.groupby(keys, sort=True, dropna=False):
        values = group_values if isinstance(group_values, tuple) else (group_values,)
        successful = group[
            group["success"].astype(bool)
            & group["official_objective"].notna()
            & group["used_container_count"].notna()
            & group["total_container_cost"].notna()
        ]
        optimal = successful[successful["status"] == "OPTIMAL"]
        if not optimal.empty:
            candidates = optimal
            reference_kind = "proven_optimal"
        elif not successful.empty:
            candidates = successful
            # This is only the best result observed inside the current corpus
            # and input fingerprint. It is not an externally established
            # best-known value and must not imply academic optimality.
            reference_kind = "best_observed"
        else:
            candidates = successful
            reference_kind = (
                "proven_infeasible"
                if bool((group["status"] == "INFEASIBLE").any())
                else "unavailable"
            )

        reference: dict[str, Any] = dict(zip(keys, values))
        if candidates.empty:
            proofs = group[group["status"] == "INFEASIBLE"].sort_values("algorithm")
            reference.update({
                "reference_kind": reference_kind,
                "reference_algorithm": None if proofs.empty else str(proofs.iloc[0]["algorithm"]),
                "reference_status": None if proofs.empty else str(proofs.iloc[0]["status"]),
                "reference_objective_value": None,
            })
        else:
            chosen = candidates.sort_values(
                ["used_container_count", "total_container_cost", "algorithm_runtime_seconds", "algorithm"],
                na_position="last",
            ).iloc[0]
            reference.update({
                "reference_kind": reference_kind,
                "reference_algorithm": str(chosen["algorithm"]),
                "reference_status": str(chosen["status"]),
                "reference_objective_value": float(chosen["objective_value"]),
            })
        references.append(reference)

    annotated = frame.merge(
        pd.DataFrame(references), on=keys, how="left", validate="many_to_one",
    )
    objective = pd.to_numeric(annotated["objective_value"], errors="coerce")
    reference = pd.to_numeric(annotated["reference_objective_value"], errors="coerce")
    gap = (objective - reference).clip(lower=0.0)
    annotated["objective_gap_absolute"] = gap
    annotated["objective_gap_percent"] = gap / reference.where(reference != 0.0) * 100.0
    return annotated


def aggregate_results(frame: pd.DataFrame, *, extra_group_keys: Sequence[str] = ()) -> pd.DataFrame:
    """Aggregate runtime over repeats and quality over one value per seed."""
    frame = frame.copy()
    _validate_benchmark_objective_invariant(frame)
    for column in (
        "feasibility_policy", "support_threshold", "minimum_exact_support_ratio", "orientation_profile",
        "orientation_candidates_evaluated", "peak_rss_bytes",
        "reporting_runtime_seconds",
        "candidate_feasibility_checks", "extreme_points_evaluated",
        "candidate_subsets_evaluated",
        "container_consolidation_candidates_evaluated",
        "secondary_utilization_concentration", "secondary_internal_void_ratio",
        "secondary_minimum_support_margin",
        "diagnostic_secondary_utilization_concentration",
        "diagnostic_secondary_internal_void_ratio",
        "diagnostic_secondary_minimum_support_margin",
    ):
        if column not in frame:
            frame[column] = None
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
        reporting_runtime_mean_seconds=("reporting_runtime_seconds", "mean"),
        peak_rss_mean_bytes=("peak_rss_bytes", "mean"),
        peak_rss_max_bytes=("peak_rss_bytes", "max"),
        candidate_feasibility_checks_mean=("candidate_feasibility_checks", "mean"),
        extreme_points_evaluated_mean=("extreme_points_evaluated", "mean"),
        candidate_subsets_evaluated_mean=("candidate_subsets_evaluated", "mean"),
        consolidation_candidates_evaluated_mean=(
            "container_consolidation_candidates_evaluated", "mean",
        ),
        distinct_solution_count=("placement_signature", "nunique"),
        feasibility_policy=("feasibility_policy", "first"),
        support_threshold=("support_threshold", "first"),
        orientation_profile=("orientation_profile", "first"),
        orientation_candidates_evaluated_mean=("orientation_candidates_evaluated", "mean"),
    )
    per_seed_aggregations: dict[str, tuple[str, str]] = {
        "objective_value": ("objective_value", "mean"),
        "used_container_count": ("used_container_count", "mean"),
        "total_container_cost": ("total_container_cost", "mean"),
        "occupied_bounding_volume_mm3": ("occupied_bounding_volume_mm3", "mean"),
        "coordinate_compactness_mm": ("coordinate_compactness_mm", "mean"),
        "minimum_exact_support_ratio": ("minimum_exact_support_ratio", "min"),
        "secondary_utilization_concentration": (
            "secondary_utilization_concentration", "mean",
        ),
        "secondary_internal_void_ratio": (
            "secondary_internal_void_ratio", "mean",
        ),
        "secondary_minimum_support_margin": (
            "secondary_minimum_support_margin", "min",
        ),
        "diagnostic_secondary_utilization_concentration": (
            "diagnostic_secondary_utilization_concentration", "mean",
        ),
        "diagnostic_secondary_internal_void_ratio": (
            "diagnostic_secondary_internal_void_ratio", "mean",
        ),
        "diagnostic_secondary_minimum_support_margin": (
            "diagnostic_secondary_minimum_support_margin", "min",
        ),
    }
    if "objective_gap_absolute" in frame.columns:
        per_seed_aggregations.update({
            "objective_gap_absolute": ("objective_gap_absolute", "mean"),
            "objective_gap_percent": ("objective_gap_percent", "mean"),
        })
    quality_source = frame[
        frame["success"].astype(bool) & frame["official_objective"].notna()
    ].copy()
    per_seed = quality_source.groupby(
        [*keys, "random_seed"], sort=True, dropna=False,
    ).agg(**per_seed_aggregations)

    quality_aggregations: dict[str, tuple[str, str]] = {
        "objective_mean": ("objective_value", "mean"),
        "objective_std": ("objective_value", "std"),
        "objective_min": ("objective_value", "min"),
        "objective_max": ("objective_value", "max"),
        "used_containers_mean": ("used_container_count", "mean"),
        "used_containers_std": ("used_container_count", "std"),
        "used_containers_min": ("used_container_count", "min"),
        "used_containers_max": ("used_container_count", "max"),
        "total_cost_mean": ("total_container_cost", "mean"),
        "total_cost_std": ("total_container_cost", "std"),
        "total_cost_min": ("total_container_cost", "min"),
        "total_cost_max": ("total_container_cost", "max"),
        "occupied_bounding_volume_mean_mm3": ("occupied_bounding_volume_mm3", "mean"),
        "occupied_bounding_volume_std_mm3": ("occupied_bounding_volume_mm3", "std"),
        "coordinate_compactness_mean_mm": ("coordinate_compactness_mm", "mean"),
        "coordinate_compactness_std_mm": ("coordinate_compactness_mm", "std"),
        "minimum_exact_support_ratio_min": ("minimum_exact_support_ratio", "min"),
        "secondary_utilization_concentration_mean": (
            "secondary_utilization_concentration", "mean",
        ),
        "secondary_internal_void_ratio_mean": (
            "secondary_internal_void_ratio", "mean",
        ),
        "secondary_minimum_support_margin_min": (
            "secondary_minimum_support_margin", "min",
        ),
        "diagnostic_secondary_utilization_concentration_mean": (
            "diagnostic_secondary_utilization_concentration", "mean",
        ),
        "diagnostic_secondary_internal_void_ratio_mean": (
            "diagnostic_secondary_internal_void_ratio", "mean",
        ),
        "diagnostic_secondary_minimum_support_margin_min": (
            "diagnostic_secondary_minimum_support_margin", "min",
        ),
    }
    if "objective_gap_absolute" in per_seed.columns:
        quality_aggregations.update({
            "objective_gap_mean_absolute": ("objective_gap_absolute", "mean"),
            "objective_gap_mean_percent": ("objective_gap_percent", "mean"),
            "objective_gap_max_percent": ("objective_gap_percent", "max"),
        })
    quality = per_seed.groupby(keys, sort=True, dropna=False).agg(**quality_aggregations)
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


def _validate_benchmark_objective_invariant(frame: pd.DataFrame) -> None:
    """Failure rows không được tham gia quality/ranking dưới bất kỳ hình thức nào."""

    required = {"success", "objective_value", "used_container_count", "total_container_cost"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError("Benchmark results are missing required columns: " + ", ".join(missing))
    failures = ~frame["success"].astype(bool)
    leaked = failures & frame["objective_value"].notna()
    for column in (
        "official_objective", "official_secondary_search_score",
        "diagnostic_secondary_search_score",
    ):
        if column in frame:
            leaked |= failures & frame[column].notna()
    if bool(leaked.any()):
        indexes = ", ".join(str(value) for value in frame.index[leaked].tolist())
        raise ValueError(
            "Failed/invalid benchmark rows must not report objective quality; "
            f"violating row indexes: {indexes}"
        )


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
    config_overrides: dict[str, Any] | None = None,
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
    scenario_algorithm_pairs = tuple(
        (algorithm_id, scenario)
        for algorithm_id in algorithms
        for scenario in selected_scenarios
        if not scenario.algorithm_ids or algorithm_id in scenario.algorithm_ids
    )
    if not scenario_algorithm_pairs:
        raise ValueError("No selected algorithm is enabled for any benchmark scenario")

    root = Path(project_root).resolve() if project_root is not None else find_project_root()
    selected_config = Path(config_path) if config_path is not None else level.default_config
    config_file = _resolve(root, selected_config)
    config = load_config(config_file)
    config = merge_config(config, dict(config_overrides or {}))
    dataset_usage = validate_dataset_usage(root, config, DatasetExecutionIntent.BENCHMARK_ACCEPTANCE)
    raw_items_path = _resolve(root, config["paths"]["raw_items_csv"])
    mapping_path = (
        _resolve(root, config["paths"]["items_source_mapping"])
        if config["paths"].get("items_source_mapping") else None
    )
    scenario_selections = {
        scenario.scenario_id: item_selection_fingerprint(
            raw_items_path,
            scenario.item_count,
            strategy=scenario.item_selection_strategy,
            seed=scenario.item_selection_seed,
            mapping_path=mapping_path,
        )
        for scenario in selected_scenarios
    }
    scenario_fingerprints = {
        scenario.scenario_id: _input_fingerprint(
            level_id=level_id,
            scenario=scenario,
            config=config,
            root=root,
            selection=scenario_selections[scenario.scenario_id],
            dataset_usage=dataset_usage,
        )
        for scenario in selected_scenarios
    }
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
                "algorithms": [
                    algorithm_id for algorithm_id in algorithms
                    if not value.algorithm_ids or algorithm_id in value.algorithm_ids
                ],
                "item_selection_strategy": value.item_selection_strategy,
                "item_selection_seed": value.item_selection_seed,
                "dataset_family": value.dataset_family,
                "scale_bucket": value.scale_bucket,
                "expected_outcome": value.expected_outcome,
                "raw_items_checksum": scenario_selections[value.scenario_id]["raw_items_checksum"],
                "selected_item_ids": scenario_selections[value.scenario_id]["selected_item_ids"],
                "selected_item_ids_checksum": scenario_selections[value.scenario_id]["selected_item_ids_checksum"],
                "input_fingerprint": scenario_fingerprints[value.scenario_id],
            }
            for value in selected_scenarios
        ],
        "repeats": repeats,
        "random_seeds": list(random_seeds),
        "environment": environment,
        "config_file": str(config_file),
        "config_overrides": dict(config_overrides or {}),
        "dataset_usage": dataset_usage.to_dict() if dataset_usage is not None else None,
    }
    write_json(benchmark_dir / "request.json", request_payload)
    resolved_config_path = run_dir / "resolved_config.yaml"
    config["benchmark"] = {"random_seeds": list(random_seeds), "repeats_per_seed": repeats}
    write_text(resolved_config_path, yaml.safe_dump(config, sort_keys=False))
    append_event(log_path, "benchmark_started", benchmark_id=benchmark_id, **request_payload)

    rows: list[dict[str, Any]] = []
    for algorithm_id, scenario in scenario_algorithm_pairs:
        fingerprint = scenario_fingerprints[scenario.scenario_id]
        for random_seed in random_seeds:
            for repeat_index in range(1, repeats + 1):
                request = ExperimentRequest(
                    level_id=level_id, algorithm_id=algorithm_id, config_path=config_file,
                    item_count=scenario.item_count, container_count=scenario.container_count, environment=environment,
                    random_seed=random_seed,
                    config_overrides=dict(config_overrides or {}),
                    item_selection_strategy=scenario.item_selection_strategy,
                    item_selection_seed=scenario.item_selection_seed,
                )
                row = {
                    "benchmark_id": benchmark_id,
                    "suite_id": suite_id or "ad_hoc",
                    "scenario_id": scenario.scenario_id,
                    "scenario_description": scenario.description,
                    "scenario_tags": ",".join(scenario.tags),
                    "dataset_family": scenario.dataset_family,
                    "scale_bucket": scenario.scale_bucket,
                    "expected_outcome": scenario.expected_outcome,
                    "item_selection_strategy": scenario.item_selection_strategy,
                    "item_selection_seed": scenario.item_selection_seed,
                    "input_fingerprint": fingerprint,
                    "experiment_fingerprint": experiment_fingerprint(
                        input_fingerprint=fingerprint,
                        algorithm_id=algorithm_id,
                        random_seed=random_seed,
                        config=config,
                    ),
                    **execute_experiment_case(request, repeat_index),
                }
                rows.append(row)
                append_event(log_path, "benchmark_case_completed", **row)

    results = pd.DataFrame(rows)
    summary = aggregate_results(
        results,
        extra_group_keys=(
            "suite_id", "scenario_id", "scenario_description", "scenario_tags",
            "item_selection_strategy", "item_selection_seed", "dataset_family",
            "scale_bucket", "expected_outcome", "input_fingerprint",
        ),
    )
    results.to_csv(benchmark_dir / "results.csv", index=False, encoding="utf-8")
    summary.to_csv(benchmark_dir / "summary.csv", index=False, encoding="utf-8")
    analysis = analyze_benchmark(summary)
    analysis.ranking.to_csv(benchmark_dir / "ranking.csv", index=False, encoding="utf-8")
    analysis.pairwise_comparison.to_csv(benchmark_dir / "pairwise_comparison.csv", index=False, encoding="utf-8")
    analysis.pareto_frontier.to_csv(benchmark_dir / "pareto_frontier.csv", index=False, encoding="utf-8")
    analysis.milp_reference_gaps.to_csv(benchmark_dir / "milp_reference_gaps.csv", index=False, encoding="utf-8")
    case_features = build_case_features(results)
    case_algorithm_summary = build_case_algorithm_summary(results)
    case_differences = build_case_differences(results)
    pairwise_outcomes = build_pairwise_outcomes(results)
    distribution_summary = build_distribution_summary(results)
    case_features.to_csv(benchmark_dir / "case_features.csv", index=False, encoding="utf-8")
    case_algorithm_summary.to_csv(
        benchmark_dir / "case_algorithm_summary.csv", index=False, encoding="utf-8",
    )
    case_differences.to_csv(
        benchmark_dir / "case_differences.csv", index=False, encoding="utf-8",
    )
    pairwise_outcomes.to_csv(benchmark_dir / "pairwise_outcomes.csv", index=False, encoding="utf-8")
    distribution_summary.to_csv(benchmark_dir / "distribution_summary.csv", index=False, encoding="utf-8")
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
        "dataset_usage": dataset_usage.to_dict() if dataset_usage is not None else None,
        "dataset_provenance": {
            "raw_items_checksum": sha256_file(raw_items_path),
            "container_catalog_checksum": (
                dataset_usage.containers_checksum if dataset_usage is not None else
                referenced_semantic_file_checksums(config, root=root).get(
                    "paths.raw_containers_csv"
                )
            ),
        },
        "source_runs": [value for value in results["experiment_run_dir"].dropna().tolist()],
        "artifacts": {
            "canonical": ["manifest.json", "resolved_config.yaml", "benchmark/request.json", "benchmark/results.csv"],
            "derived": [
                "benchmark/summary.csv", "benchmark/summary.json", "benchmark/ranking.csv",
                "benchmark/pairwise_comparison.csv", "benchmark/pareto_frontier.csv",
                "benchmark/milp_reference_gaps.csv", "benchmark/case_features.csv",
                "benchmark/case_algorithm_summary.csv", "benchmark/case_differences.csv",
                "benchmark/pairwise_outcomes.csv", "benchmark/distribution_summary.csv",
                "reports/summary.md",
            ],
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
        f"\n{analysis.report_markdown}"
    ))
    append_event(log_path, "benchmark_completed", benchmark_id=benchmark_id, status=status, cases=len(results), successful=succeeded)
    return BenchmarkResult(benchmark_id, run_dir, results, summary, analysis)
