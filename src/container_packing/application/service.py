"""Stable application boundary shared by interactive frontends."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from ..algorithms.registry import get_algorithm
from ..benchmarks import BenchmarkResult, BenchmarkScenario, run_benchmark
from ..data_loader import load_config
from ..experiments.contracts import ExperimentRequest
from ..experiments.runner import run_experiment
from ..instance_data import ITEM_SELECTION_STRATEGIES
from ..levels.registry import get_level
from ..runtime.project import find_project_root
from ..source_adapter import SourceAdapterError, load_csv_source
from ..schemas import RunResult


@dataclass(frozen=True)
class InstanceLimits:
    available_items: int
    configured_containers: int


@dataclass(frozen=True)
class RunArtifact:
    run_id: str
    run_dir: Path
    level_id: str
    algorithm_id: str
    status: str
    validation_status: str
    created_at_utc: str
    item_count: int | None
    container_count: int | None


@dataclass(frozen=True)
class BenchmarkArtifact:
    run_id: str
    run_dir: Path
    level_id: str
    status: str
    created_at_utc: str
    case_count: int
    successful_case_count: int
    random_seeds: tuple[int, ...]
    repeats_per_seed: int | None


def _root(root: str | Path | None = None) -> Path:
    return Path(root).resolve() if root is not None else find_project_root(__file__)


def _resolve(root: Path, path: str | Path) -> Path:
    candidate = Path(path)
    return candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()


def get_instance_limits(config_path: str | Path, *, root: str | Path | None = None) -> InstanceLimits:
    project_root = _root(root)
    config = load_config(_resolve(project_root, config_path))
    raw_items = _resolve(project_root, config["paths"]["raw_items_csv"])
    mapping_value = config["paths"].get("items_source_mapping")
    mapping = _resolve(project_root, mapping_value) if mapping_value else None
    try:
        available_items = len(load_csv_source(raw_items, mapping).frame)
    except SourceAdapterError as exc:
        raise ValueError(f"Cannot determine item limit from {raw_items}: {exc}") from exc
    configured_containers = len(config.get("containers", []))
    if configured_containers <= 0:
        raise ValueError(f"Config {config_path} does not define any base containers")
    return InstanceLimits(available_items=available_items, configured_containers=configured_containers)


def build_experiment_request(
    *,
    level_id: str,
    algorithm_id: str,
    item_count: int,
    container_count: int,
    environment: str = "local",
    random_seed: int | None = None,
    algorithm_parameters: dict[str, Any] | None = None,
    config_overrides: dict[str, Any] | None = None,
    config_path: str | Path | None = None,
    root: str | Path | None = None,
) -> ExperimentRequest:
    if item_count <= 0 or container_count <= 0:
        raise ValueError("item_count and container_count must be positive")
    if random_seed is not None and random_seed < 0:
        raise ValueError("random_seed must be zero or greater")
    if environment not in {"local", "colab", "kaggle"}:
        raise ValueError(f"Unsupported environment: {environment}")
    level = get_level(level_id)
    algorithm = get_algorithm(algorithm_id)
    if algorithm_id not in level.supported_algorithms or level_id not in algorithm.supported_levels:
        raise ValueError(f"{algorithm_id} is not compatible with {level_id}")
    project_root = _root(root)
    selected_config = level.default_config if config_path is None else Path(config_path)
    resolved_config = _resolve(project_root, selected_config)
    limits = get_instance_limits(resolved_config, root=project_root)
    if item_count > limits.available_items:
        raise ValueError(f"Requested {item_count} items but only {limits.available_items} are available")
    return ExperimentRequest(
        level_id=level_id,
        algorithm_id=algorithm_id,
        config_path=resolved_config,
        item_count=item_count,
        container_count=container_count,
        environment=environment,
        random_seed=random_seed,
        algorithm_parameters=dict(algorithm_parameters or {}),
        config_overrides=dict(config_overrides or {}),
    )


def resolve_result_run_dir(result: RunResult, *, root: str | Path | None = None) -> Path:
    value = result.metadata.get("run_dir")
    if not value:
        raise ValueError("Experiment result has no persisted run directory")
    return _resolve(_root(root), str(value))


def execute_experiment(request: ExperimentRequest) -> RunResult:
    """Execute through the registry-driven pipeline used by every frontend."""
    return run_experiment(request)


def execute_benchmark_comparison(
    *,
    level_id: str,
    algorithm_ids: list[str] | tuple[str, ...],
    item_count: int,
    container_count: int,
    seeds: list[int] | tuple[int, ...],
    repeats: int = 1,
    environment: str = "local",
    config_path: str | Path | None = None,
    root: str | Path | None = None,
    item_selection_strategy: str = "prefix",
    item_selection_seed: int | None = None,
    config_overrides: dict[str, Any] | None = None,
) -> BenchmarkResult:
    """Run selected algorithms on one strictly shared, independently validated instance."""
    algorithms = tuple(str(value) for value in algorithm_ids)
    if len(algorithms) < 2:
        raise ValueError("A benchmark comparison requires at least two algorithms")
    if len(algorithms) != len(set(algorithms)):
        raise ValueError("Benchmark algorithms must not contain duplicates")
    if repeats <= 0:
        raise ValueError("repeats must be positive")
    random_seeds = tuple(int(value) for value in seeds)
    if not random_seeds or any(value < 0 for value in random_seeds):
        raise ValueError("seeds must contain one or more non-negative integers")
    if len(random_seeds) != len(set(random_seeds)):
        raise ValueError("seeds must not contain duplicates; use repeats for timing repetition")
    if item_selection_strategy not in ITEM_SELECTION_STRATEGIES:
        raise ValueError(f"Unsupported item selection strategy: {item_selection_strategy}")
    if item_selection_strategy == "stable_random" and item_selection_seed is None:
        raise ValueError("stable_random item selection requires item_selection_seed")

    project_root = _root(root)
    level = get_level(level_id)
    selected_config = level.default_config if config_path is None else Path(config_path)
    resolved_config = _resolve(project_root, selected_config)
    for algorithm_id in algorithms:
        build_experiment_request(
            level_id=level_id,
            algorithm_id=algorithm_id,
            item_count=item_count,
            container_count=container_count,
            environment=environment,
            random_seed=random_seeds[0],
            config_path=resolved_config,
            root=project_root,
        )
    scenario = BenchmarkScenario(
        scenario_id=f"interactive_i{item_count}_c{container_count}",
        description=f"Interactive comparison: {item_count} items, {container_count} containers",
        item_count=item_count,
        container_count=container_count,
        tags=("interactive", "same_instance"),
        item_selection_strategy=item_selection_strategy,
        item_selection_seed=item_selection_seed,
    )
    return run_benchmark(
        level_id=level_id,
        algorithm_ids=algorithms,
        item_counts=(item_count,),
        container_counts=(container_count,),
        repeats=repeats,
        seeds=random_seeds,
        config_path=resolved_config,
        environment=environment,
        project_root=project_root,
        scenarios=(scenario,),
        suite_id=f"{level_id}_interactive_comparison",
        config_overrides=dict(config_overrides or {}),
    )


def discover_runs(
    level_id: str,
    *,
    root: str | Path | None = None,
    limit: int = 50,
) -> tuple[RunArtifact, ...]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    get_level(level_id)
    project_root = _root(root)
    runs_root = (project_root / "outputs" / level_id / "runs").resolve()
    if not runs_root.is_dir():
        return ()
    artifacts: list[RunArtifact] = []
    for manifest_path in sorted(runs_root.glob("*/manifest.json"), key=lambda value: value.stat().st_mtime, reverse=True):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if manifest.get("level") != level_id:
            continue
        metrics_path = manifest_path.parent / "metrics" / "metrics.json"
        metrics: dict[str, Any] = {}
        if metrics_path.is_file():
            try:
                metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                metrics = {}
        artifacts.append(RunArtifact(
            run_id=str(manifest.get("run_id", manifest_path.parent.name)),
            run_dir=manifest_path.parent,
            level_id=level_id,
            algorithm_id=str(manifest.get("algorithm", "unknown")),
            status=str(manifest.get("status", "unknown")),
            validation_status=str(manifest.get("validation_status", "unknown")),
            created_at_utc=str(manifest.get("created_at_utc", "")),
            item_count=metrics.get("n_items"),
            container_count=metrics.get("n_containers_available"),
        ))
        if len(artifacts) >= limit:
            break
    return tuple(artifacts)


def discover_benchmark_runs(
    level_id: str,
    *,
    root: str | Path | None = None,
    limit: int = 50,
) -> tuple[BenchmarkArtifact, ...]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    get_level(level_id)
    project_root = _root(root)
    runs_root = (project_root / "outputs" / level_id / "runs").resolve()
    if not runs_root.is_dir():
        return ()
    artifacts: list[BenchmarkArtifact] = []
    for manifest_path in sorted(runs_root.glob("*/manifest.json"), key=lambda value: value.stat().st_mtime, reverse=True):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if manifest.get("level") != level_id or manifest.get("run_type") != "benchmark":
            continue
        benchmark_dir = manifest_path.parent / "benchmark"
        if not (benchmark_dir / "summary.csv").is_file() or not (benchmark_dir / "results.csv").is_file():
            continue
        seeds = manifest.get("random_seeds", [])
        artifacts.append(BenchmarkArtifact(
            run_id=str(manifest.get("run_id", manifest_path.parent.name)),
            run_dir=manifest_path.parent,
            level_id=level_id,
            status=str(manifest.get("status", "unknown")),
            created_at_utc=str(manifest.get("created_at_utc", "")),
            case_count=int(manifest.get("case_count", 0) or 0),
            successful_case_count=int(manifest.get("successful_case_count", 0) or 0),
            random_seeds=tuple(int(value) for value in seeds),
            repeats_per_seed=manifest.get("repeats_per_seed"),
        ))
        if len(artifacts) >= limit:
            break
    return tuple(artifacts)
