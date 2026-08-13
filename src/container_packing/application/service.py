"""Stable application boundary shared by interactive frontends."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import pandas as pd

from ..algorithms.registry import get_algorithm
from ..benchmarks import BenchmarkResult, BenchmarkScenario, run_benchmark
from ..data_loader import load_config
from ..dataset_usage import DatasetExecutionIntent, validate_dataset_usage
from ..experiments.contracts import ExperimentRequest
from ..experiments.runner import run_experiment
from ..instance_data import (
    ITEM_SELECTION_STRATEGIES,
    load_configured_container_catalog,
    select_item_rows,
)
from ..levels.registry import get_level
from ..runtime.project import find_project_root
from ..algorithms.search.inventory import normalize_container_inventory
from ..algorithms.search.precheck import (
    assess_capacity_within_container_limit,
    estimate_container_lower_bound,
    run_hard_precheck,
)
from ..schemas import Container, Item
from ..source_adapter import SourceAdapterError, load_csv_source
from ..schemas import RunResult
from ..provenance import sha256_file


@dataclass(frozen=True)
class InstanceLimits:
    available_items: int
    configured_containers: int


@dataclass(frozen=True)
class ContainerInventorySummary:
    """Read-only inventory evidence suitable for a frontend preview."""

    ready: bool
    physical_container_count: int
    equivalent_type_count: int
    available_container_count: int
    unavailable_container_count: int
    total_available_volume_m3: float
    total_available_payload_kg: float
    type_rows: tuple[dict[str, object], ...]
    inventory_fingerprint: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class InventoryRequestPreview:
    """Evidence chỉ đọc cho request inventory trước khi chạy solver."""

    item_count: int
    selected_item_ids_checksum: str
    total_item_volume_m3: float
    total_item_weight_kg: float
    physical_container_count: int
    equivalent_type_count: int
    volume_lower_bound: int
    payload_lower_bound: int
    aggregate_lower_bound: int
    initial_used_container_count: int
    max_used_container_count: int
    recommended_max_used_container_count: int
    estimated_unique_composition_count: int
    precheck_valid: bool
    precheck_issue_count: int
    capacity_limit_valid: bool
    attainable_volume_m3: float
    attainable_payload_kg: float
    volume_deficit_m3: float
    payload_deficit_kg: float


@dataclass(frozen=True)
class BenchmarkInputProvenance:
    """Nguồn dữ liệu đã resolve dùng cho preview benchmark trên frontend."""

    config_file: str
    dataset_profile_id: str | None
    raw_items_checksum: str
    container_catalog_checksum: str | None
    available_item_count: int
    physical_container_count: int


@dataclass(frozen=True)
class ActiveDataContext:
    """Nguồn dữ liệu duy nhất được chia sẻ bởi experiment và benchmark trên UI."""

    level_id: str
    config_file: str
    profile_id: str | None
    available_item_count: int
    physical_container_count: int
    raw_items_checksum: str
    container_catalog_checksum: str | None
    usage_class: str
    solver_acceptance_allowed: bool


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
    execution_count: int
    successful_execution_count: int
    random_seeds: tuple[int, ...]
    repeats_per_seed: int | None
    run_type: str = "benchmark"
    suite_id: str | None = None
    config_file: str | None = None
    dataset_profile_id: str | None = None
    raw_items_checksum: str | None = None
    container_catalog_checksum: str | None = None


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
    raw_containers_value = config.get("paths", {}).get("raw_containers_csv")
    if raw_containers_value:
        raw_containers = _resolve(project_root, raw_containers_value)
        try:
            configured_containers = len(
                pd.read_csv(raw_containers, encoding="utf-8-sig")
            )
        except (OSError, pd.errors.ParserError) as exc:
            raise ValueError(
                f"Cannot determine container limit from {raw_containers}: {exc}"
            ) from exc
    else:
        configured_containers = len(config.get("containers", []))
    if configured_containers <= 0:
        raise ValueError(f"Config {config_path} does not define any base containers")
    return InstanceLimits(available_items=available_items, configured_containers=configured_containers)


def get_benchmark_input_provenance(
    config_path: str | Path,
    *,
    root: str | Path | None = None,
) -> BenchmarkInputProvenance:
    """Resolve checksum/profile trước benchmark mà không tạo output hay gọi solver."""
    project_root = _root(root)
    resolved_config = _resolve(project_root, config_path)
    config = load_config(resolved_config)
    usage = validate_dataset_usage(
        project_root, config, DatasetExecutionIntent.BENCHMARK_ACCEPTANCE,
    )
    limits = get_instance_limits(resolved_config, root=project_root)
    raw_items = _resolve(project_root, config["paths"]["raw_items_csv"])
    raw_containers_value = config.get("paths", {}).get("raw_containers_csv")
    catalog_checksum = (
        sha256_file(_resolve(project_root, raw_containers_value))
        if raw_containers_value else None
    )
    return BenchmarkInputProvenance(
        config_file=str(resolved_config),
        dataset_profile_id=usage.profile_id if usage is not None else None,
        raw_items_checksum=sha256_file(raw_items),
        container_catalog_checksum=(
            usage.containers_checksum if usage is not None else catalog_checksum
        ),
        available_item_count=limits.available_items,
        physical_container_count=limits.configured_containers,
    )


def resolve_active_data_context(
    level_id: str,
    config_path: str | Path,
    *,
    root: str | Path | None = None,
) -> ActiveDataContext:
    """Resolve một data context bất biến, đủ điều kiện cho solver và benchmark."""
    project_root = _root(root)
    get_level(level_id)
    resolved_config = _resolve(project_root, config_path)
    config = load_config(resolved_config)
    configured_level = str(config.get("project", {}).get("level_id", level_id))
    if configured_level != level_id:
        raise ValueError(
            f"Active data config belongs to {configured_level}, not requested {level_id}"
        )
    usage = validate_dataset_usage(
        project_root, config, DatasetExecutionIntent.SOLVER_EXPERIMENT,
    )
    limits = get_instance_limits(resolved_config, root=project_root)
    raw_items = _resolve(project_root, config["paths"]["raw_items_csv"])
    raw_containers_value = config.get("paths", {}).get("raw_containers_csv")
    catalog_checksum = (
        sha256_file(_resolve(project_root, raw_containers_value))
        if raw_containers_value else None
    )
    return ActiveDataContext(
        level_id=level_id,
        config_file=str(resolved_config),
        profile_id=usage.profile_id if usage is not None else None,
        available_item_count=limits.available_items,
        physical_container_count=limits.configured_containers,
        raw_items_checksum=sha256_file(raw_items),
        container_catalog_checksum=(
            usage.containers_checksum if usage is not None else catalog_checksum
        ),
        usage_class=usage.usage_class if usage is not None else "canonical_raw",
        solver_acceptance_allowed=(
            usage.solver_acceptance_allowed if usage is not None else True
        ),
    )


def get_container_inventory_summary(
    config_path: str | Path,
    *,
    root: str | Path | None = None,
) -> ContainerInventorySummary:
    """Summarize the full configured catalog without invoking a solver.

    Missing generated files are reported as data readiness rather than being
    silently replaced by the small inline catalog.
    """
    project_root = _root(root)
    resolved_config = _resolve(project_root, config_path)
    try:
        config = load_config(resolved_config)
        level_id = str(config.get("project", {}).get("level_id", "level_01"))
        frame, _ = load_configured_container_catalog(
            project_root, config, level_id=level_id
        )
        containers = [
            Container(
                container_id=str(row.container_id),
                length_mm=float(row.length_mm),
                width_mm=float(row.width_mm),
                height_mm=float(row.height_mm),
                max_weight_kg=float(row.max_weight_kg),
                cost=float(row.cost),
                availability=int(row.availability),
                volume_m3=float(row.volume_m3),
                source=row._asdict(),
            )
            for row in frame.itertuples(index=False)
        ]
        inventory = normalize_container_inventory(containers)
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        return ContainerInventorySummary(
            ready=False,
            physical_container_count=0,
            equivalent_type_count=0,
            available_container_count=0,
            unavailable_container_count=0,
            total_available_volume_m3=0.0,
            total_available_payload_kg=0.0,
            type_rows=(),
            inventory_fingerprint=None,
            error=str(exc),
        )

    type_rows = tuple({
        "type_id": group.type_id,
        "equivalent_type_id": group.type_id,
        "declared_type_ids": ", ".join(group.declared_type_ids),
        "display_type_id": group.display_type_id,
        "representative_container_id": group.representative.container_id,
        "quantity": group.quantity,
        "length_mm": group.representative.length_mm,
        "width_mm": group.representative.width_mm,
        "height_mm": group.representative.height_mm,
        "volume_m3": group.representative.volume_m3,
        "max_weight_kg": group.representative.max_weight_kg,
        "cost": group.representative.cost,
        "constraint_profile": group.constraint_profile,
    } for group in inventory.groups)
    available = inventory.available_containers
    return ContainerInventorySummary(
        ready=True,
        physical_container_count=len(containers),
        equivalent_type_count=inventory.equivalent_type_count,
        available_container_count=inventory.physical_container_count,
        unavailable_container_count=len(inventory.unavailable_container_ids),
        total_available_volume_m3=sum(value.volume_m3 for value in available),
        total_available_payload_kg=sum(value.max_weight_kg for value in available),
        type_rows=type_rows,
        inventory_fingerprint=inventory.inventory_fingerprint,
    )


def get_inventory_request_preview(
    config_path: str | Path,
    *,
    item_count: int,
    initial_used_container_count: int,
    max_used_container_count: int,
    item_selection_strategy: str = "prefix",
    item_selection_seed: int | None = None,
    root: str | Path | None = None,
) -> InventoryRequestPreview:
    """Tính lower bound/checksum từ source mà không ghi processed data hay gọi solver."""
    if initial_used_container_count <= 0 or max_used_container_count <= 0:
        raise ValueError("Inventory preview container counts must be positive")
    if initial_used_container_count > max_used_container_count:
        raise ValueError("Initial container count cannot exceed maximum container count")
    project_root = _root(root)
    config = load_config(_resolve(project_root, config_path))
    raw_items = _resolve(project_root, config["paths"]["raw_items_csv"])
    mapping_value = config["paths"].get("items_source_mapping")
    mapping = _resolve(project_root, mapping_value) if mapping_value else None
    source = load_csv_source(raw_items, mapping).frame
    selected = select_item_rows(
        source,
        item_count,
        strategy=item_selection_strategy,
        seed=item_selection_seed,
    )
    items = [
        Item(
            item_id=str(row.id_item),
            length_mm=float(row.length),
            width_mm=float(row.width),
            height_mm=float(row.height),
            weight_kg=float(row.weight),
            level1_order=index,
            source=row._asdict(),
        )
        for index, row in enumerate(selected.itertuples(index=False), start=1)
    ]
    frame, _ = load_configured_container_catalog(
        project_root,
        config,
        level_id=str(config.get("project", {}).get("level_id", "level_01")),
    )
    containers = [
        Container(
            container_id=str(row.container_id),
            length_mm=float(row.length_mm),
            width_mm=float(row.width_mm),
            height_mm=float(row.height_mm),
            max_weight_kg=float(row.max_weight_kg),
            cost=float(row.cost),
            availability=int(row.availability),
            volume_m3=float(row.volume_m3),
            source=row._asdict(),
        )
        for row in frame.itertuples(index=False)
    ]
    inventory = normalize_container_inventory(containers)
    lower_bound = estimate_container_lower_bound(items, inventory)
    precheck = run_hard_precheck(items, inventory)
    capacity_limit = assess_capacity_within_container_limit(
        items, inventory, max_used_container_count,
    )
    item_ids = [item.item_id for item in items]
    checksum = sha256(json.dumps(
        item_ids, ensure_ascii=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()
    recommended = min(
        inventory.physical_container_count,
        max(
            lower_bound.aggregate_lower_bound + 2,
            ceil(lower_bound.aggregate_lower_bound * 1.25),
        ),
    )
    return InventoryRequestPreview(
        item_count=len(items),
        selected_item_ids_checksum=checksum,
        total_item_volume_m3=sum(item.volume_m3 for item in items),
        total_item_weight_kg=sum(item.weight_kg for item in items),
        physical_container_count=inventory.physical_container_count,
        equivalent_type_count=inventory.equivalent_type_count,
        volume_lower_bound=lower_bound.volume_lower_bound,
        payload_lower_bound=lower_bound.payload_lower_bound,
        aggregate_lower_bound=lower_bound.aggregate_lower_bound,
        initial_used_container_count=initial_used_container_count,
        max_used_container_count=max_used_container_count,
        recommended_max_used_container_count=recommended,
        estimated_unique_composition_count=_composition_count(
            tuple(group.quantity for group in inventory.groups),
            initial_used_container_count,
            max_used_container_count,
        ),
        precheck_valid=precheck.valid,
        precheck_issue_count=len(precheck.issues),
        capacity_limit_valid=capacity_limit.valid,
        attainable_volume_m3=capacity_limit.attainable_volume_m3,
        attainable_payload_kg=capacity_limit.attainable_payload_kg,
        volume_deficit_m3=capacity_limit.volume_deficit_m3,
        payload_deficit_kg=capacity_limit.payload_deficit_kg,
    )


def _composition_count(
    quantities: tuple[int, ...], minimum: int, maximum: int,
) -> int:
    """Đếm composition bounded theo type bằng dynamic programming."""
    ways = [0] * (maximum + 1)
    ways[0] = 1
    for quantity in quantities:
        updated = [0] * (maximum + 1)
        for used, count in enumerate(ways):
            if not count:
                continue
            for take in range(min(quantity, maximum - used) + 1):
                updated[used + take] += count
        ways = updated
    return sum(ways[minimum:maximum + 1])


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
    item_selection_strategy: str = "prefix",
    item_selection_seed: int | None = None,
) -> ExperimentRequest:
    if item_count <= 0 or container_count <= 0:
        raise ValueError("item_count and container_count must be positive")
    if random_seed is not None and random_seed < 0:
        raise ValueError("random_seed must be zero or greater")
    if environment not in {"local", "colab", "kaggle"}:
        raise ValueError(f"Unsupported environment: {environment}")
    if item_selection_strategy not in ITEM_SELECTION_STRATEGIES:
        raise ValueError(
            f"Unsupported item selection strategy: {item_selection_strategy}"
        )
    if item_selection_strategy == "stable_random" and item_selection_seed is None:
        raise ValueError("stable_random item selection requires item_selection_seed")
    level = get_level(level_id)
    algorithm = get_algorithm(algorithm_id)
    if algorithm_id not in level.supported_algorithms or level_id not in algorithm.supported_levels:
        raise ValueError(f"{algorithm_id} is not compatible with {level_id}")
    project_root = _root(root)
    selected_config = level.config_for_algorithm(algorithm_id) if config_path is None else Path(config_path)
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
        item_selection_strategy=item_selection_strategy,
        item_selection_seed=(
            item_selection_seed
            if item_selection_strategy == "stable_random"
            else None
        ),
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
    search_config = dict((config_overrides or {}).get("container_search", {}))
    inventory_enabled = bool(search_config.get("enabled", False))
    maximum_count = int(search_config.get("max_used_container_count", container_count))
    if inventory_enabled:
        scenario_id = f"interactive_i{item_count}_start{container_count}_max{maximum_count}"
        scenario_description = (
            f"Interactive comparison: {item_count} items, inventory search starts at "
            f"{container_count} and may use at most {maximum_count} containers"
        )
    else:
        scenario_id = f"interactive_i{item_count}_c{container_count}"
        scenario_description = (
            f"Interactive comparison: {item_count} items, {container_count} containers"
        )
    scenario = BenchmarkScenario(
        scenario_id=scenario_id,
        description=scenario_description,
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
    config_file: str | Path | None = None,
    dataset_profile_id: str | None = None,
    expected_raw_items_checksum: str | None = None,
    expected_container_catalog_checksum: str | None = None,
    include_all_profiles: bool = False,
) -> tuple[BenchmarkArtifact, ...]:
    if limit <= 0:
        raise ValueError("limit must be positive")
    get_level(level_id)
    project_root = _root(root)
    runs_root = (project_root / "outputs" / level_id / "runs").resolve()
    if not runs_root.is_dir():
        return ()
    expected_config = (
        str(_resolve(project_root, config_file)) if config_file is not None else None
    )
    artifacts: list[BenchmarkArtifact] = []
    for manifest_path in sorted(runs_root.glob("*/manifest.json"), key=lambda value: value.stat().st_mtime, reverse=True):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        run_type = str(manifest.get("run_type", ""))
        if manifest.get("level") != level_id or run_type not in {"benchmark", "benchmark_corpus"}:
            continue
        benchmark_dir = manifest_path.parent / "benchmark"
        if not (benchmark_dir / "summary.csv").is_file() or not (benchmark_dir / "results.csv").is_file():
            continue
        request: dict[str, Any] = {}
        request_path = benchmark_dir / "request.json"
        if request_path.is_file():
            try:
                request = json.loads(request_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                request = {}
        scenarios = request.get("scenarios", [])
        first_scenario = scenarios[0] if isinstance(scenarios, list) and scenarios else {}
        usage = manifest.get("dataset_usage") or request.get("dataset_usage") or {}
        if not usage and run_type == "benchmark_corpus":
            profiles = manifest.get("dataset_profiles", [])
            if isinstance(profiles, list) and profiles:
                usage = profiles[0]
        profile_id = str(usage.get("profile_id", "")) or None
        resolved_config = str(manifest.get("config_file", request.get("config_file", ""))) or None
        provenance = manifest.get("dataset_provenance") or {}
        raw_items_checksum = provenance.get("raw_items_checksum") or first_scenario.get("raw_items_checksum")
        catalog_checksum = provenance.get("container_catalog_checksum")
        if run_type == "benchmark_corpus" and isinstance(usage, dict):
            raw_items_checksum = raw_items_checksum or usage.get("items_checksum")
            catalog_checksum = catalog_checksum or usage.get("containers_checksum")
        checksums = first_scenario.get("referenced_file_checksums")
        if isinstance(checksums, dict):
            catalog_checksum = checksums.get("paths.raw_containers_csv")
        if not include_all_profiles:
            if run_type == "benchmark" and expected_config is not None and resolved_config != expected_config:
                continue
            if dataset_profile_id is not None and profile_id != dataset_profile_id:
                continue
            if (
                expected_raw_items_checksum is not None
                and expected_raw_items_checksum != str(raw_items_checksum or "")
            ):
                continue
            if (
                expected_container_catalog_checksum is not None
                and expected_container_catalog_checksum != str(catalog_checksum or "")
            ):
                continue
        seeds = manifest.get("random_seeds", [])
        if run_type == "benchmark_corpus":
            test_case_count = int(manifest.get("case_count", 0) or 0)
            execution_count = int(manifest.get("execution_count", 0) or 0)
            successful_execution_count = int(
                manifest.get("successful_execution_count", 0) or 0
            )
        else:
            test_case_count = (
                len(scenarios)
                if isinstance(scenarios, list) and scenarios
                else int(manifest.get("case_count", 0) or 0)
            )
            execution_count = int(manifest.get("case_count", 0) or 0)
            successful_execution_count = int(
                manifest.get("successful_case_count", 0) or 0
            )
        artifacts.append(BenchmarkArtifact(
            run_id=str(manifest.get("run_id", manifest_path.parent.name)),
            run_dir=manifest_path.parent,
            level_id=level_id,
            status=str(manifest.get("status", "unknown")),
            created_at_utc=str(manifest.get("created_at_utc", "")),
            case_count=test_case_count,
            successful_case_count=successful_execution_count,
            execution_count=execution_count,
            successful_execution_count=successful_execution_count,
            random_seeds=tuple(int(value) for value in seeds),
            repeats_per_seed=manifest.get("repeats_per_seed"),
            run_type=run_type,
            suite_id=str(manifest.get("suite_id") or manifest.get("corpus_id") or "") or None,
            config_file=resolved_config,
            dataset_profile_id=profile_id,
            raw_items_checksum=str(raw_items_checksum) if raw_items_checksum else None,
            container_catalog_checksum=str(catalog_checksum) if catalog_checksum else None,
        ))
        if len(artifacts) >= limit:
            break
    return tuple(artifacts)
