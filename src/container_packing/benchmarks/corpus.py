"""Corpus benchmark có tên, cấu hình versioned và quality gap kiểm toán được."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from copy import deepcopy
import re
from typing import Any

import pandas as pd
import yaml

from ..algorithms.registry import get_algorithm
from ..data_loader import load_config, merge_config
from ..dataset_usage import DatasetExecutionIntent, validate_dataset_usage
from ..experiments.contracts import ExperimentRequest
from ..levels.registry import get_level
from ..instance_data import ITEM_SELECTION_STRATEGIES
from ..instance_data import item_selection_fingerprint
from ..provenance import runtime_metadata, sha256_file
from ..reporting import OUTPUT_SCHEMA_VERSION, write_json, write_text
from ..runtime.project import find_project_root
from ..runtime.run_context import create_benchmark_corpus_directory
from ..runtime.structured_logging import append_event
from .runner import _seed_values, aggregate_results, annotate_reference_gaps, execute_experiment_case
from .distribution import (
    build_case_algorithm_summary,
    build_case_differences,
    build_case_features,
    build_determinism_evidence,
    build_distribution_summary,
    build_pairwise_outcomes,
    build_repair_comparison,
)
from .fingerprint import semantic_input_fingerprint
from .matrix import expand_corpus_matrix
from .suites import BenchmarkScenario

_CASE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_EXPECTED_OUTCOMES = {"feasible", "infeasible"}


@dataclass(frozen=True)
class CorpusCase:
    case_id: str
    group: str
    difficulty: str
    item_count: int
    container_count: int
    expected_outcome: str
    algorithms: tuple[str, ...]
    config_path: Path
    description: str = ""
    item_selection_strategy: str = "prefix"
    item_selection_seed: int | None = None
    dataset_family: str = "unspecified"
    scale_bucket: str = "unspecified"
    config_overrides: dict[str, Any] | None = None
    comparison_group: str | None = None
    variant_id: str | None = None
    benchmark_stratum: str = "unclassified"
    volume_lower_bound: int | None = None
    payload_lower_bound: int | None = None
    aggregate_lower_bound: int | None = None
    physical_inventory_count: int | None = None
    planned_selected_item_ids_checksum: str | None = None


@dataclass(frozen=True)
class BenchmarkCorpus:
    schema_version: str
    corpus_id: str
    level_id: str
    environment: str
    seeds: tuple[int, ...]
    repeats: int
    cases: tuple[CorpusCase, ...]
    source_path: Path


@dataclass(frozen=True)
class BenchmarkCorpusResult:
    corpus_id: str
    run_id: str
    run_dir: Path
    results: pd.DataFrame
    summary: pd.DataFrame
    ranking: pd.DataFrame
    references: pd.DataFrame

    @property
    def successful(self) -> bool:
        return bool(len(self.results)) and bool(self.results["expectation_met"].all())


def _resolve(root: Path, value: str | Path) -> Path:
    candidate = Path(value)
    return candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()


def _positive(value: Any, name: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return parsed


def _validate_algorithms(level_id: str, values: Any) -> tuple[str, ...]:
    if not isinstance(values, list) or not values:
        raise ValueError("Each corpus case must define one or more algorithms")
    algorithms = tuple(str(value) for value in values)
    if len(set(algorithms)) != len(algorithms):
        raise ValueError("Corpus case algorithms must not contain duplicates")
    level = get_level(level_id)
    for algorithm_id in algorithms:
        definition = get_algorithm(algorithm_id)
        if algorithm_id not in level.supported_algorithms or level_id not in definition.supported_levels:
            raise ValueError(f"{algorithm_id} is not compatible with {level_id}")
    return algorithms


def load_benchmark_corpus(
    corpus_path: str | Path, *, project_root: str | Path | None = None,
) -> BenchmarkCorpus:
    root = Path(project_root).resolve() if project_root is not None else find_project_root()
    source_path = _resolve(root, corpus_path)
    try:
        payload = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Cannot read benchmark corpus {source_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Benchmark corpus {source_path} must contain a YAML mapping")
    schema_version = str(payload.get("schema_version", ""))
    if schema_version not in {"1.0", "1.1"}:
        raise ValueError(f"Unsupported benchmark corpus schema_version: {schema_version!r}")
    corpus_id = str(payload.get("corpus_id", ""))
    if not _CASE_ID.fullmatch(corpus_id):
        raise ValueError("corpus_id must use lowercase letters, numbers, underscores, or hyphens")
    level_id = str(payload.get("level_id", ""))
    get_level(level_id)
    environment = str(payload.get("environment", "local"))
    if environment not in {"local", "colab", "kaggle"}:
        raise ValueError(f"Unsupported corpus environment: {environment}")
    seeds = _seed_values(payload.get("seeds", [42]))
    repeats = _positive(payload.get("repeats", 1), "repeats")
    default_config = payload.get("default_config")
    raw_cases = payload.get("cases")
    raw_matrix = payload.get("matrix")
    if raw_cases is not None and raw_matrix is not None:
        raise ValueError("Benchmark corpus must define cases or matrix, not both")
    if raw_matrix is not None:
        if schema_version != "1.1":
            raise ValueError("Benchmark corpus matrix requires schema_version 1.1")
        raw_cases = expand_corpus_matrix(
            raw_matrix,
            root=root,
            level_id=level_id,
            default_config=default_config,
        )
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("Benchmark corpus must define one or more cases")
    cases: list[CorpusCase] = []
    seen: set[str] = set()
    for index, raw_case in enumerate(raw_cases, start=1):
        if not isinstance(raw_case, dict):
            raise ValueError(f"Corpus case {index} must be a mapping")
        case_id = str(raw_case.get("case_id", ""))
        if not _CASE_ID.fullmatch(case_id):
            raise ValueError(f"Invalid case_id at corpus case {index}: {case_id!r}")
        if case_id in seen:
            raise ValueError(f"Duplicate corpus case_id: {case_id}")
        seen.add(case_id)
        expected = str(raw_case.get("expected_outcome", "feasible"))
        if expected not in _EXPECTED_OUTCOMES:
            raise ValueError(f"Unsupported expected_outcome for {case_id}: {expected}")
        configured = raw_case.get("config", default_config)
        if not configured:
            raise ValueError(f"Corpus case {case_id} has no config path")
        config_path = _resolve(root, str(configured))
        load_config(config_path)
        config_overrides = raw_case.get("config_overrides", {})
        if not isinstance(config_overrides, dict):
            raise ValueError(f"config_overrides for {case_id} must be a mapping")
        item_count = _positive(raw_case.get("item_count"), f"{case_id}.item_count")
        container_count = _positive(
            raw_case.get("container_count"), f"{case_id}.container_count",
        )
        dataset_family = str(raw_case.get("dataset_family", "unspecified"))
        if dataset_family == "mpv_fixed_orientation_exact_support":
            resolved_case_config = merge_config(load_config(config_path), config_overrides)
            search = resolved_case_config.get("container_search", {})
            maximum = int(search.get("max_used_container_count", container_count))
            if maximum > container_count:
                raise ValueError(
                    f"MPV corpus case {case_id} allows {maximum} containers but its "
                    f"materialized physical inventory contains only {container_count}"
                )
        item_selection_strategy = str(raw_case.get("item_selection", "prefix"))
        if item_selection_strategy not in ITEM_SELECTION_STRATEGIES:
            raise ValueError(f"Unsupported item_selection for {case_id}: {item_selection_strategy}")
        item_selection_seed = raw_case.get("selection_seed")
        if item_selection_seed is not None:
            item_selection_seed = int(item_selection_seed)
            if item_selection_seed < 0:
                raise ValueError(f"selection_seed for {case_id} must be zero or greater")
        if item_selection_strategy == "stable_random" and item_selection_seed is None:
            raise ValueError(f"stable_random corpus case {case_id} requires selection_seed")
        cases.append(CorpusCase(
            case_id=case_id,
            group=str(raw_case.get("group", "unclassified")),
            difficulty=str(raw_case.get("difficulty", "unclassified")),
            item_count=item_count,
            container_count=container_count,
            expected_outcome=expected,
            algorithms=_validate_algorithms(level_id, raw_case.get("algorithms")),
            config_path=config_path,
            description=str(raw_case.get("description", "")),
            item_selection_strategy=item_selection_strategy,
            item_selection_seed=item_selection_seed,
            dataset_family=dataset_family,
            scale_bucket=str(raw_case.get("scale_bucket", "unspecified")),
            config_overrides=dict(config_overrides),
            comparison_group=(
                str(raw_case["comparison_group"]).strip()
                if raw_case.get("comparison_group") else None
            ),
            variant_id=(
                str(raw_case["variant_id"]).strip()
                if raw_case.get("variant_id") else None
            ),
            benchmark_stratum=str(raw_case.get("benchmark_stratum", "unclassified")),
            volume_lower_bound=(
                int(raw_case["volume_lower_bound"])
                if raw_case.get("volume_lower_bound") is not None else None
            ),
            payload_lower_bound=(
                int(raw_case["payload_lower_bound"])
                if raw_case.get("payload_lower_bound") is not None else None
            ),
            aggregate_lower_bound=(
                int(raw_case["aggregate_lower_bound"])
                if raw_case.get("aggregate_lower_bound") is not None else None
            ),
            physical_inventory_count=(
                int(raw_case["physical_inventory_count"])
                if raw_case.get("physical_inventory_count") is not None else None
            ),
            planned_selected_item_ids_checksum=(
                str(raw_case["planned_selected_item_ids_checksum"])
                if raw_case.get("planned_selected_item_ids_checksum") else None
            ),
        ))
        if bool(cases[-1].comparison_group) != bool(cases[-1].variant_id):
            raise ValueError(
                f"Corpus case {case_id} must define comparison_group and variant_id together"
            )
    return BenchmarkCorpus(
        schema_version=schema_version,
        corpus_id=corpus_id,
        level_id=level_id,
        environment=environment,
        seeds=seeds,
        repeats=repeats,
        cases=tuple(cases),
        source_path=source_path,
    )


def _observed_outcome(status: str, success: bool) -> str:
    if success:
        return "feasible"
    if status in {"INFEASIBLE", "INFEASIBLE_HEURISTIC", "PRECHECK_FAILED"}:
        return "infeasible"
    return "error"


def _ranking(summary: pd.DataFrame) -> pd.DataFrame:
    feasible = summary[(summary["expected_outcome"] == "feasible") & (summary["success_rate"] > 0)].copy()
    if feasible.empty:
        return feasible
    feasible["objective_gap_mean_percent"] = pd.to_numeric(
        feasible["objective_gap_mean_percent"], errors="coerce",
    )
    feasible = feasible.sort_values(
        ["case_id", "objective_gap_mean_percent", "used_containers_mean", "total_cost_mean",
         "algorithm_runtime_mean_seconds", "algorithm"],
        na_position="last",
    )
    feasible.insert(0, "rank", feasible.groupby("case_id", sort=False).cumcount() + 1)
    return feasible


def build_selection_overlap(
    selections_by_case: dict[str, dict[str, Any]],
) -> pd.DataFrame:
    """Measure overlap between selected item sets without claiming independence."""
    columns = [
        "benchmark_stratum", "item_count", "case_a", "case_b",
        "selection_seed_a", "selection_seed_b", "intersection_count",
        "union_count", "overlap_fraction_of_case", "jaccard_similarity",
    ]
    records: list[dict[str, Any]] = []
    values = sorted(
        selections_by_case.values(),
        key=lambda value: (value["benchmark_stratum"], value["item_count"], value["case_id"]),
    )
    for index, left in enumerate(values):
        if left["item_selection_strategy"] != "stable_random":
            continue
        left_ids = set(left["selected_item_ids"])
        for right in values[index + 1:]:
            if (
                right["benchmark_stratum"] != left["benchmark_stratum"]
                or right["item_count"] != left["item_count"]
                or right["item_selection_strategy"] != "stable_random"
            ):
                continue
            right_ids = set(right["selected_item_ids"])
            intersection = len(left_ids & right_ids)
            union = len(left_ids | right_ids)
            records.append({
                "benchmark_stratum": left["benchmark_stratum"],
                "item_count": left["item_count"],
                "case_a": left["case_id"],
                "case_b": right["case_id"],
                "selection_seed_a": left["item_selection_seed"],
                "selection_seed_b": right["item_selection_seed"],
                "intersection_count": intersection,
                "union_count": union,
                "overlap_fraction_of_case": intersection / max(1, len(left_ids)),
                "jaccard_similarity": intersection / max(1, union),
            })
    return pd.DataFrame(records, columns=columns)


def run_benchmark_corpus(
    corpus_path: str | Path, *, project_root: str | Path | None = None,
) -> BenchmarkCorpusResult:
    root = Path(project_root).resolve() if project_root is not None else find_project_root()
    corpus = load_benchmark_corpus(corpus_path, project_root=root)
    configs = {case.config_path for case in corpus.cases}
    dataset_profiles = [
        evidence.to_dict()
        for config_path in sorted(configs)
        if (evidence := validate_dataset_usage(
            root, load_config(config_path), DatasetExecutionIntent.BENCHMARK_ACCEPTANCE,
        )) is not None
    ]
    output_roots = {
        _resolve(root, load_config(path)["paths"].get("output_root", "outputs")) for path in configs
    }
    if len(output_roots) != 1:
        raise ValueError("Every corpus case must resolve to the same output root")
    output_root = next(iter(output_roots))
    run_id, run_dir = create_benchmark_corpus_directory(
        output_root, corpus.level_id, corpus.corpus_id, corpus.seeds,
    )
    benchmark_dir = run_dir / "benchmark"
    log_path = run_dir / "logs" / "run.log"
    benchmark_dir.mkdir(parents=True)
    log_path.parent.mkdir(parents=True)

    case_catalog = pd.DataFrame([{
        "case_id": case.case_id,
        "group": case.group,
        "difficulty": case.difficulty,
        "item_count": case.item_count,
        "container_count": case.container_count,
        "expected_outcome": case.expected_outcome,
        "algorithms": ",".join(case.algorithms),
        "config_file": str(case.config_path),
        "description": case.description,
        "item_selection_strategy": case.item_selection_strategy,
        "item_selection_seed": case.item_selection_seed,
        "dataset_family": case.dataset_family,
        "scale_bucket": case.scale_bucket,
        "config_overrides": case.config_overrides or {},
        "comparison_group": case.comparison_group,
        "variant_id": case.variant_id,
        "benchmark_stratum": case.benchmark_stratum,
        "volume_lower_bound": case.volume_lower_bound,
        "payload_lower_bound": case.payload_lower_bound,
        "aggregate_lower_bound": case.aggregate_lower_bound,
        "physical_inventory_count": case.physical_inventory_count,
        "planned_selected_item_ids_checksum": case.planned_selected_item_ids_checksum,
        "initial_container_count": (
            (case.config_overrides or {}).get("container_search", {}).get(
                "initial_used_container_count", case.container_count,
            )
        ),
        "max_used_container_count": (
            (case.config_overrides or {}).get("container_search", {}).get(
                "max_used_container_count", case.container_count,
            )
        ),
    } for case in corpus.cases])
    resolved_payload = {
        "schema_version": corpus.schema_version,
        "corpus_id": corpus.corpus_id,
        "level_id": corpus.level_id,
        "environment": corpus.environment,
        "seeds": list(corpus.seeds),
        "repeats": corpus.repeats,
        "cases": case_catalog.to_dict(orient="records"),
    }
    resolved_config_path = run_dir / "resolved_config.yaml"
    write_text(resolved_config_path, yaml.safe_dump(resolved_payload, sort_keys=False, allow_unicode=True))
    write_json(benchmark_dir / "request.json", resolved_payload)
    case_catalog.to_csv(benchmark_dir / "case_catalog.csv", index=False, encoding="utf-8")
    append_event(log_path, "benchmark_corpus_started", run_id=run_id, **resolved_payload)

    rows: list[dict[str, Any]] = []
    selections_by_case: dict[str, dict[str, Any]] = {}
    for case in corpus.cases:
        case_config = merge_config(load_config(case.config_path), case.config_overrides or {})
        case_usage = validate_dataset_usage(
            root, case_config, DatasetExecutionIntent.BENCHMARK_ACCEPTANCE,
        )
        raw_items = _resolve(root, case_config["paths"]["raw_items_csv"])
        mapping_value = case_config["paths"].get("items_source_mapping")
        mapping_path = _resolve(root, mapping_value) if mapping_value else None
        scenario = BenchmarkScenario(
            scenario_id=case.case_id, description=case.description or case.case_id,
            item_count=case.item_count, container_count=case.container_count,
            item_selection_strategy=case.item_selection_strategy,
            item_selection_seed=case.item_selection_seed,
            dataset_family=case.dataset_family, scale_bucket=case.scale_bucket,
            expected_outcome=case.expected_outcome,
        )
        selection = item_selection_fingerprint(
            raw_items, case.item_count, strategy=case.item_selection_strategy,
            seed=case.item_selection_seed, mapping_path=mapping_path,
        )
        if (
            case.planned_selected_item_ids_checksum is not None
            and selection["selected_item_ids_checksum"]
            != case.planned_selected_item_ids_checksum
        ):
            raise ValueError(
                f"Corpus case {case.case_id} no longer matches its materialized item "
                "selection checksum; reload the versioned corpus catalog"
            )
        selections_by_case[case.case_id] = {
            "case_id": case.case_id,
            "benchmark_stratum": case.benchmark_stratum,
            "item_count": case.item_count,
            "item_selection_strategy": case.item_selection_strategy,
            "item_selection_seed": case.item_selection_seed,
            "selected_item_ids": tuple(selection["selected_item_ids"]),
        }
        fingerprint = semantic_input_fingerprint(
            level_id=corpus.level_id, scenario=scenario, config=case_config,
            root=root, selection=selection, dataset_usage=case_usage,
        )
        comparison_fingerprint: str | None = None
        if case.comparison_group:
            comparison_config = deepcopy(case_config)
            # Repair la treatment cua A/B, khong phai mot phan cua input vat ly.
            # Tat ca search settings khac van nam trong fingerprint doi chung.
            comparison_config.setdefault("container_search", {}).pop("consolidation", None)
            comparison_scenario = BenchmarkScenario(
                scenario_id=case.comparison_group,
                description=case.comparison_group,
                item_count=case.item_count,
                container_count=case.container_count,
                item_selection_strategy=case.item_selection_strategy,
                item_selection_seed=case.item_selection_seed,
                dataset_family=case.dataset_family,
                scale_bucket=case.scale_bucket,
                expected_outcome=case.expected_outcome,
            )
            comparison_fingerprint = semantic_input_fingerprint(
                level_id=corpus.level_id,
                scenario=comparison_scenario,
                config=comparison_config,
                root=root,
                selection=selection,
                dataset_usage=case_usage,
            )
        for algorithm_id in case.algorithms:
            for random_seed in corpus.seeds:
                for repeat_index in range(1, corpus.repeats + 1):
                    request = ExperimentRequest(
                        level_id=corpus.level_id,
                        algorithm_id=algorithm_id,
                        config_path=case.config_path,
                        item_count=case.item_count,
                        container_count=case.container_count,
                        environment=corpus.environment,
                        random_seed=random_seed,
                        item_selection_strategy=case.item_selection_strategy,
                        item_selection_seed=case.item_selection_seed,
                        config_overrides=case.config_overrides,
                    )
                    row = execute_experiment_case(request, repeat_index)
                    observed = _observed_outcome(str(row["status"]), bool(row["success"]))
                    row.update({
                        "corpus_id": corpus.corpus_id,
                        "corpus_run_id": run_id,
                        "case_id": case.case_id,
                        "scenario_id": case.case_id,
                        "suite_id": corpus.corpus_id,
                        "scenario_description": case.description,
                        "scenario_tags": "",
                        "input_fingerprint": fingerprint,
                        "item_selection_strategy": case.item_selection_strategy,
                        "item_selection_seed": case.item_selection_seed,
                        "group": case.group,
                        "difficulty": case.difficulty,
                        "dataset_family": case.dataset_family,
                        "scale_bucket": case.scale_bucket,
                        "expected_outcome": case.expected_outcome,
                        "observed_outcome": observed,
                        "expectation_met": observed == case.expected_outcome,
                        "infeasibility_proven": row["status"] == "INFEASIBLE",
                        "comparison_group": case.comparison_group,
                        "benchmark_variant_id": case.variant_id,
                        "comparison_input_fingerprint": comparison_fingerprint,
                        "benchmark_stratum": case.benchmark_stratum,
                    })
                    if case.aggregate_lower_bound is not None:
                        row.setdefault("volume_lower_bound", case.volume_lower_bound)
                        row.setdefault("payload_lower_bound", case.payload_lower_bound)
                        row.setdefault("aggregate_lower_bound", case.aggregate_lower_bound)
                    rows.append(row)
                    append_event(log_path, "benchmark_corpus_case_completed", **row)

    results = annotate_reference_gaps(pd.DataFrame(rows), instance_keys=("case_id",))
    group_keys = ("case_id", "group", "difficulty", "expected_outcome")
    summary = aggregate_results(results, extra_group_keys=group_keys)
    expectation = results.groupby(
        ["level", "algorithm", "item_count", "container_count", *group_keys],
        sort=True,
        dropna=False,
    ).agg(
        expectation_met_rate=("expectation_met", "mean"),
        infeasibility_proof_count=("infeasibility_proven", "sum"),
    ).reset_index()
    summary = summary.merge(
        expectation,
        on=["level", "algorithm", "item_count", "container_count", *group_keys],
        how="left",
        validate="one_to_one",
    )
    references = results[[
        "case_id", "group", "difficulty", "item_count", "container_count", "expected_outcome",
        "reference_kind", "reference_algorithm", "reference_status", "reference_objective_value",
    ]].drop_duplicates().sort_values("case_id")
    summary = summary.merge(
        references[[
            "case_id", "reference_kind", "reference_algorithm", "reference_status",
            "reference_objective_value",
        ]],
        on="case_id",
        how="left",
        validate="many_to_one",
    )
    ranking = _ranking(summary)
    case_features = build_case_features(results)
    case_algorithm_summary = build_case_algorithm_summary(results)
    case_differences = build_case_differences(results)
    pairwise_outcomes = build_pairwise_outcomes(results)
    distribution_summary = build_distribution_summary(results)
    determinism_evidence = build_determinism_evidence(results)
    repair_comparison = build_repair_comparison(results)
    selection_overlap = build_selection_overlap(selections_by_case)

    results.to_csv(benchmark_dir / "results.csv", index=False, encoding="utf-8")
    summary.to_csv(benchmark_dir / "summary.csv", index=False, encoding="utf-8")
    ranking.to_csv(benchmark_dir / "ranking.csv", index=False, encoding="utf-8")
    references.to_csv(benchmark_dir / "references.csv", index=False, encoding="utf-8")
    case_features.to_csv(benchmark_dir / "case_features.csv", index=False, encoding="utf-8")
    case_algorithm_summary.to_csv(
        benchmark_dir / "case_algorithm_summary.csv", index=False, encoding="utf-8",
    )
    case_differences.to_csv(
        benchmark_dir / "case_differences.csv", index=False, encoding="utf-8",
    )
    pairwise_outcomes.to_csv(benchmark_dir / "pairwise_outcomes.csv", index=False, encoding="utf-8")
    distribution_summary.to_csv(benchmark_dir / "distribution_summary.csv", index=False, encoding="utf-8")
    determinism_evidence.to_csv(benchmark_dir / "determinism_evidence.csv", index=False, encoding="utf-8")
    repair_comparison.to_csv(benchmark_dir / "repair_comparison.csv", index=False, encoding="utf-8")
    selection_overlap.to_csv(benchmark_dir / "selection_overlap.csv", index=False, encoding="utf-8")
    write_json(benchmark_dir / "summary.json", {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "corpus_id": corpus.corpus_id,
        "rows": summary.to_dict(orient="records"),
    })

    successful = int(results["expectation_met"].sum())
    status = "SUCCESS" if successful == len(results) else ("PARTIAL" if successful else "FAILED")
    config_checksums = {str(path): sha256_file(path) for path in sorted(configs)}
    manifest = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "project": "3d-container-packing",
        "run_type": "benchmark_corpus",
        "level": corpus.level_id,
        "run_id": run_id,
        "corpus_id": corpus.corpus_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "environment": corpus.environment,
        "random_seed": corpus.seeds[0] if len(corpus.seeds) == 1 else None,
        "random_seeds": list(corpus.seeds),
        "repeats_per_seed": corpus.repeats,
        "status": status,
        "case_count": len(corpus.cases),
        "execution_count": len(results),
        "successful_execution_count": successful,
        "config_file": str(corpus.source_path),
        "config_file_checksum": sha256_file(corpus.source_path),
        "case_config_checksums": config_checksums,
        "dataset_profiles": dataset_profiles,
        "resolved_config_checksum": sha256_file(resolved_config_path),
        "source_runs": [value for value in results["experiment_run_dir"].dropna().tolist()],
        "artifacts": {
            "canonical": [
                "manifest.json", "resolved_config.yaml", "benchmark/request.json",
                "benchmark/case_catalog.csv", "benchmark/results.csv",
            ],
            "derived": [
                "benchmark/summary.csv", "benchmark/summary.json", "benchmark/ranking.csv",
                "benchmark/references.csv", "reports/summary.md",
                "benchmark/case_features.csv", "benchmark/pairwise_outcomes.csv",
                "benchmark/case_algorithm_summary.csv", "benchmark/case_differences.csv",
                "benchmark/distribution_summary.csv",
                "benchmark/determinism_evidence.csv", "benchmark/repair_comparison.csv",
                "benchmark/selection_overlap.csv",
            ],
            "diagnostics": ["logs/run.log"],
        },
        **runtime_metadata(root),
    }
    write_json(run_dir / "manifest.json", manifest)
    report_dir = run_dir / "reports"
    report_dir.mkdir()
    proven = int((references["reference_kind"] == "proven_optimal").sum())
    infeasible = int((references["reference_kind"] == "proven_infeasible").sum())
    write_text(report_dir / "summary.md", (
        f"# Benchmark corpus {corpus.corpus_id}\n\n"
        f"- Status: {status}\n- Cases: {len(corpus.cases)}\n- Executions: {len(results)}\n"
        f"- Expectations met: {successful}\n- Proven-optimal references: {proven}\n"
        f"- Proven-infeasible cases: {infeasible}\n- Level: {corpus.level_id}\n"
        f"- Seeds: {', '.join(str(value) for value in corpus.seeds)}\n"
        f"- Repeats per seed: {corpus.repeats}\n"
    ))
    append_event(
        log_path, "benchmark_corpus_completed", run_id=run_id, status=status,
        executions=len(results), expectations_met=successful,
    )
    return BenchmarkCorpusResult(
        corpus.corpus_id, run_id, run_dir, results, summary, ranking, references,
    )
