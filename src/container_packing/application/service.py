"""Stable application boundary shared by interactive frontends."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import pandas as pd

from ..algorithms.registry import get_algorithm
from ..data_loader import load_config
from ..experiments.contracts import ExperimentRequest
from ..experiments.runner import run_experiment
from ..levels.registry import get_level
from ..runtime.project import find_project_root
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
    run_type: str
    status: str
    created_at_utc: str
    corpus_id: str | None
    case_count: int
    execution_count: int


@dataclass(frozen=True)
class BenchmarkTables:
    results: pd.DataFrame
    summary: pd.DataFrame
    ranking: pd.DataFrame
    references: pd.DataFrame


def _root(root: str | Path | None = None) -> Path:
    return find_project_root(root) if root is not None else find_project_root(__file__)


def _resolve(root: Path, path: str | Path) -> Path:
    candidate = Path(path)
    return candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()


def get_instance_limits(config_path: str | Path, *, root: str | Path | None = None) -> InstanceLimits:
    project_root = _root(root)
    config = load_config(_resolve(project_root, config_path))
    raw_items = _resolve(project_root, config["paths"]["raw_items_csv"])
    try:
        available_items = len(pd.read_csv(raw_items, encoding="utf-8-sig", usecols=["id_item"]))
    except (OSError, ValueError, pd.errors.ParserError) as exc:
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
    )


def resolve_result_run_dir(result: RunResult, *, root: str | Path | None = None) -> Path:
    value = result.metadata.get("run_dir")
    if not value:
        raise ValueError("Experiment result has no persisted run directory")
    return _resolve(_root(root), str(value))


def execute_experiment(request: ExperimentRequest) -> RunResult:
    """Execute through the registry-driven pipeline used by every frontend."""
    return run_experiment(request)


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
        if manifest.get("run_type", "experiment") != "experiment":
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


def discover_benchmarks(
    level_id: str,
    *,
    root: str | Path | None = None,
    limit: int = 25,
) -> tuple[BenchmarkArtifact, ...]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    get_level(level_id)
    runs_root = (_root(root) / "outputs" / level_id / "runs").resolve()
    if not runs_root.is_dir():
        return ()
    artifacts: list[BenchmarkArtifact] = []
    manifests = sorted(
        runs_root.glob("*/manifest.json"), key=lambda value: value.stat().st_mtime, reverse=True,
    )
    for manifest_path in manifests:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        run_type = str(manifest.get("run_type", ""))
        if manifest.get("level") != level_id or run_type not in {"benchmark", "benchmark_corpus"}:
            continue
        artifacts.append(BenchmarkArtifact(
            run_id=str(manifest.get("run_id", manifest_path.parent.name)),
            run_dir=manifest_path.parent,
            level_id=level_id,
            run_type=run_type,
            status=str(manifest.get("status", "unknown")),
            created_at_utc=str(manifest.get("created_at_utc", "")),
            corpus_id=None if manifest.get("corpus_id") is None else str(manifest["corpus_id"]),
            case_count=int(manifest.get("case_count", 0)),
            execution_count=int(manifest.get("execution_count", manifest.get("case_count", 0))),
        ))
        if len(artifacts) >= limit:
            break
    return tuple(artifacts)


def load_benchmark_tables(
    run_dir: str | Path, *, root: str | Path | None = None,
) -> BenchmarkTables:
    directory = _resolve(_root(root), run_dir)
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError(f"Benchmark manifest does not exist: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read benchmark manifest {manifest_path}: {exc}") from exc
    if manifest.get("run_type") not in {"benchmark", "benchmark_corpus"}:
        raise ValueError(f"Run directory is not a benchmark: {directory}")
    benchmark_dir = directory / "benchmark"

    def read_required(name: str) -> pd.DataFrame:
        path = benchmark_dir / name
        if not path.is_file():
            raise ValueError(f"Missing benchmark artifact: {path}")
        try:
            return pd.read_csv(path)
        except (OSError, pd.errors.ParserError) as exc:
            raise ValueError(f"Cannot read benchmark artifact {path}: {exc}") from exc

    def read_optional(name: str) -> pd.DataFrame:
        path = benchmark_dir / name
        return pd.read_csv(path) if path.is_file() else pd.DataFrame()

    return BenchmarkTables(
        results=read_required("results.csv"),
        summary=read_required("summary.csv"),
        ranking=read_optional("ranking.csv"),
        references=read_optional("references.csv"),
    )
