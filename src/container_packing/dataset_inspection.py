"""Bounded-memory inspection for generated physical-instance datasets."""

from __future__ import annotations

import csv
import gc
import json
import re
import shutil
import threading
import time
import tracemalloc
from dataclasses import asdict, dataclass
from enum import Enum
from itertools import zip_longest
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import psutil
import yaml

from .dataset_usage import ValidatedGenerationManifest, validate_generation_manifest_files
from .algorithms.search import (
    InventorySearchLimits,
    LazyRankedContainerSubsetPolicy,
    estimate_container_lower_bound,
    normalize_container_inventory,
    run_hard_precheck,
)
from .provenance import runtime_metadata
from .reporting import write_json
from .runtime.run_context import create_run_directory
from .runtime.structured_logging import append_event
from .schemas import Container, Item
from .source_adapter import load_csv_source


class InspectionMode(str, Enum):
    STREAM = "stream"
    MATERIALIZE = "materialize"
    BOTH = "both"


class InspectionIntent(str, Enum):
    DATASET_INSPECTION = "dataset_inspection"
    INVENTORY_SCALE_GATE = "inventory_scale_gate"


@dataclass(frozen=True)
class InspectionIssue:
    phase: str
    code: str
    message: str


@dataclass(frozen=True)
class PhaseResult:
    phase: str
    status: str
    runtime_seconds: float
    rows_processed: int
    bytes_processed: int
    rows_per_second: float
    megabytes_per_second: float
    initial_rss_mb: float
    peak_rss_mb: float
    rss_delta_mb: float
    python_heap_peak_mb: float


@dataclass(frozen=True)
class DatasetInspectionRequest:
    manifest_path: Path
    level_id: str = "level_08"
    mode: InspectionMode = InspectionMode.STREAM
    output_root: Path = Path("outputs")
    project_root: Path = Path(".")
    intent: InspectionIntent = InspectionIntent.DATASET_INSPECTION
    inventory_preview_item_count: int = 20
    inventory_preview_candidates: int = 32


@dataclass(frozen=True)
class InventoryScaleGateEvidence:
    status: str
    runtime_seconds: float
    peak_rss_mb: float
    python_heap_peak_mb: float
    preview_item_count: int
    physical_container_count: int
    equivalent_type_count: int
    lower_bound: int
    hard_precheck_valid: bool
    candidate_count: int
    candidate_signatures: tuple[tuple[str, ...], ...]
    subset_policy_metadata: dict[str, Any]
    issue: str | None = None


@dataclass(frozen=True)
class DatasetInspectionResult:
    status: str
    run_id: str
    run_dir: Path
    profile_id: str
    usage_class: str
    capacity_qualification: str
    provenance: PhaseResult
    stream: PhaseResult | None
    materialize: PhaseResult | None
    inventory_scale_gate: InventoryScaleGateEvidence | None
    issues: tuple[InspectionIssue, ...]

    @property
    def valid(self) -> bool:
        return self.status == "VALID"


class _MemoryTracker:
    def __init__(self) -> None:
        self._process = psutil.Process()
        self._initial = self._process.memory_info().rss
        self._peak = self._initial
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._sample, daemon=True)

    def start(self) -> None:
        tracemalloc.start()
        self._thread.start()

    def stop(self) -> tuple[float, float, float, float]:
        self._stop.set()
        self._thread.join(timeout=1.0)
        self._peak = max(self._peak, self._process.memory_info().rss)
        _, heap_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        divisor = 1024.0 * 1024.0
        return (
            self._initial / divisor,
            self._peak / divisor,
            (self._peak - self._initial) / divisor,
            heap_peak / divisor,
        )

    def _sample(self) -> None:
        while not self._stop.wait(0.05):
            self._peak = max(self._peak, self._process.memory_info().rss)


def inspect_generated_dataset(request: DatasetInspectionRequest) -> DatasetInspectionResult:
    """Inspect one generated profile without invoking preprocessing or a solver."""
    project_root = request.project_root.resolve()
    output_root = request.output_root
    if not output_root.is_absolute():
        output_root = project_root / output_root
    if not re.fullmatch(r"level_\d{2}", request.level_id):
        raise ValueError("level_id must use the level_XX naming convention")
    peek = _peek_manifest(request.manifest_path)
    run_id, run_dir = create_run_directory(
        output_root.resolve(), request.level_id, "dataset_inspection",
        int(peek.get("item_count", 0) or 0), int(peek.get("container_count", 0) or 0),
        int(peek.get("seed", 0) or 0),
    )
    (run_dir / "logs").mkdir()
    (run_dir / "reports").mkdir()
    (run_dir / "input_snapshot").mkdir()
    resolved_config = {
        "manifest_path": str(request.manifest_path.resolve()),
        "level_id": request.level_id,
        "mode": request.mode.value,
        "intent": request.intent.value,
        "output_root": str(output_root.resolve()),
    }
    (run_dir / "resolved_config.yaml").write_text(
        yaml.safe_dump(resolved_config, sort_keys=False), encoding="utf-8",
    )
    if request.manifest_path.is_file():
        shutil.copyfile(request.manifest_path, run_dir / "input_snapshot" / "generation_manifest.json")
    append_event(run_dir / "logs" / "run.log", "dataset_inspection_started", run_id=run_id,
                 mode=request.mode.value, manifest=str(request.manifest_path))
    issues: list[InspectionIssue] = []
    validated: ValidatedGenerationManifest | None = None

    def provenance_action() -> tuple[int, int]:
        nonlocal validated
        validated = validate_generation_manifest_files(request.manifest_path)
        return len(validated.file_paths), sum(path.stat().st_size for path in validated.file_paths.values())

    provenance = _run_phase("provenance", provenance_action, issues)
    stream_result: PhaseResult | None = None
    materialize_result: PhaseResult | None = None
    if provenance.status == "VALID" and validated is not None:
        if request.mode in {InspectionMode.STREAM, InspectionMode.BOTH}:
            stream_result = _run_phase(
                "stream", lambda: _stream_inspect(validated), issues,
            )
        if request.mode in {InspectionMode.MATERIALIZE, InspectionMode.BOTH}:
            if stream_result is None or stream_result.status == "VALID":
                gc.collect()
                materialize_result = _run_phase(
                    "materialize", lambda: _materialize_inspect(validated, project_root), issues,
                )
    inventory_gate: InventoryScaleGateEvidence | None = None
    if (
        request.intent == InspectionIntent.INVENTORY_SCALE_GATE
        and provenance.status == "VALID"
        and validated is not None
    ):
        inventory_gate = _inventory_scale_gate(
            validated,
            project_root,
            item_limit=request.inventory_preview_item_count,
            candidate_limit=request.inventory_preview_candidates,
        )
        if inventory_gate.status != "VALID":
            issues.append(InspectionIssue("inventory_scale_gate", "GATE_FAILED", inventory_gate.issue or "unknown error"))
    payload = validated.payload if validated is not None else peek
    status = "VALID" if not issues else "INVALID"
    result = DatasetInspectionResult(
        status=status,
        run_id=run_id,
        run_dir=run_dir,
        profile_id=str(payload.get("profile_id", "unknown")),
        usage_class=str(payload.get("usage_class", "unknown")),
        capacity_qualification=str(payload.get("capacity_qualification", "unknown")),
        provenance=provenance,
        stream=stream_result,
        materialize=materialize_result,
        inventory_scale_gate=inventory_gate,
        issues=tuple(issues[:100]),
    )
    report = _result_payload(result)
    write_json(run_dir / "reports" / "dataset_inspection.json", report)
    if inventory_gate is not None:
        write_json(run_dir / "reports" / "inventory_scale_gate.json", asdict(inventory_gate))
    write_json(run_dir / "manifest.json", {
        "schema_version": "1.0",
        "run_type": "dataset_inspection",
        "level": request.level_id,
        "run_id": run_id,
        "status": status,
        "profile_id": result.profile_id,
        "usage_class": result.usage_class,
        "capacity_qualification": result.capacity_qualification,
        "objective_value": None,
        "solver_invoked": False,
        "generation_manifest": str(request.manifest_path.resolve()),
        "artifacts": {
            "canonical": [
                "manifest.json", "resolved_config.yaml",
                "input_snapshot/generation_manifest.json", "reports/dataset_inspection.json",
            ],
            "diagnostics": (["logs/run.log"] + (
                ["reports/inventory_scale_gate.json"] if inventory_gate is not None else []
            )),
        },
        **runtime_metadata(project_root),
    })
    append_event(run_dir / "logs" / "run.log", "dataset_inspection_completed", run_id=run_id,
                 status=status, issue_count=len(issues))
    return result


def _run_phase(
    phase: str,
    action: Callable[[], tuple[int, int]],
    issues: list[InspectionIssue],
) -> PhaseResult:
    tracker = _MemoryTracker()
    tracker.start()
    started = time.perf_counter()
    rows = 0
    byte_count = 0
    status = "VALID"
    try:
        rows, byte_count = action()
    except Exception as exc:
        status = "INVALID"
        issues.append(InspectionIssue(phase, type(exc).__name__, str(exc)))
    runtime = time.perf_counter() - started
    initial, peak, delta, heap_peak = tracker.stop()
    return PhaseResult(
        phase=phase,
        status=status,
        runtime_seconds=runtime,
        rows_processed=rows,
        bytes_processed=byte_count,
        rows_per_second=rows / runtime if runtime > 0 else 0.0,
        megabytes_per_second=(byte_count / (1024 * 1024)) / runtime if runtime > 0 else 0.0,
        initial_rss_mb=initial,
        peak_rss_mb=peak,
        rss_delta_mb=delta,
        python_heap_peak_mb=heap_peak,
    )


def _stream_inspect(validated: ValidatedGenerationManifest) -> tuple[int, int]:
    files = validated.file_paths
    payload = validated.payload
    templates = _catalog_by(files["item_templates"], "item_template_id")
    container_types = _catalog_by(files["container_types"], "container_type_id")
    total_volume = 0.0
    total_weight = 0.0
    item_rows = 0
    with _reader(files["item_instances"]) as instances, _reader(files["delivery"]) as deliveries, \
            _reader(files["solver_items"]) as solver_items:
        for ordinal, trio in enumerate(zip_longest(instances, deliveries, solver_items), start=1):
            instance, delivery, solver = trio
            if instance is None or delivery is None or solver is None:
                raise ValueError("Item instance, delivery and solver CSV row counts differ")
            item_id = f"ITEM-{ordinal:09d}"
            if instance.get("item_id") != item_id or delivery.get("item_id") != item_id or solver.get("id_item") != item_id:
                raise ValueError(f"Physical item identity mismatch at row {ordinal + 1}")
            template_id = str(instance.get("item_template_id", ""))
            template = templates.get(template_id)
            if template is None or solver.get("item_template_id") != template_id:
                raise ValueError(f"Unknown or mismatched item template at row {ordinal + 1}")
            _same_number(instance, "actual_weight_kg", solver, "weight", ordinal)
            for template_field, solver_field in (
                ("length_mm", "length"), ("width_mm", "width"), ("height_mm", "height"),
                ("nesting_height_mm", "nesting_height"), ("max_stackability", "max_stackability"),
            ):
                _same_number(template, template_field, solver, solver_field, ordinal)
            for field in ("stackability_code", "forced_orientation"):
                if str(template.get(field, "")) != str(solver.get(field, "")):
                    raise ValueError(f"Template field {field} mismatch at item row {ordinal + 1}")
            for field in ("delivery_priority", "delivery_stop_id", "delivery_data_source"):
                if str(delivery.get(field, "")) != str(solver.get(field, "")):
                    raise ValueError(f"Delivery field {field} mismatch at item row {ordinal + 1}")
            if _positive_int(delivery.get("delivery_priority"), "delivery_priority", ordinal) <= 0:
                raise ValueError(f"Invalid delivery priority at item row {ordinal + 1}")
            length = _positive_float(solver.get("length"), "length", ordinal)
            width = _positive_float(solver.get("width"), "width", ordinal)
            height = _positive_float(solver.get("height"), "height", ordinal)
            weight = _positive_float(solver.get("weight"), "weight", ordinal)
            total_volume += length * width * height / 1_000_000_000.0
            total_weight += weight
            item_rows += 1
    fleet_volume = 0.0
    fleet_payload = 0.0
    container_rows = 0
    with _reader(files["container_instances"]) as instances, _reader(files["solver_containers"]) as solver_rows:
        for ordinal, pair in enumerate(zip_longest(instances, solver_rows), start=1):
            instance, solver = pair
            if instance is None or solver is None:
                raise ValueError("Container instance and solver CSV row counts differ")
            if instance.get("container_id") != solver.get("container_id"):
                raise ValueError(f"Container identity mismatch at row {ordinal + 1}")
            type_id = str(instance.get("container_type_id", ""))
            template = container_types.get(type_id)
            if template is None or solver.get("container_type_id") != type_id:
                raise ValueError(f"Unknown or mismatched container type at row {ordinal + 1}")
            for field in ("length_mm", "width_mm", "height_mm", "max_weight_kg", "cost", "volume_m3"):
                _same_number(template, field, solver, field, ordinal)
                _same_number(instance, field, solver, field, ordinal)
            fleet_volume += _positive_float(solver.get("volume_m3"), "volume_m3", ordinal)
            fleet_payload += _positive_float(solver.get("max_weight_kg"), "max_weight_kg", ordinal)
            container_rows += 1
    if item_rows != int(payload.get("item_count", -1)):
        raise ValueError(f"Item row count {item_rows} does not match manifest item_count")
    if container_rows != int(payload.get("container_count", -1)):
        raise ValueError(f"Container row count {container_rows} does not match manifest container_count")
    capacity = payload.get("capacity", {})
    for actual, key in (
        (total_volume, "total_item_volume_m3"), (total_weight, "total_item_weight_kg"),
        (fleet_volume, "total_fleet_volume_m3"), (fleet_payload, "total_fleet_payload_kg"),
    ):
        _assert_close(actual, capacity.get(key), f"capacity.{key}")
    _assert_close(fleet_volume / total_volume, payload.get("actual_volume_margin_ratio"),
                  "actual_volume_margin_ratio")
    _assert_close(fleet_payload / total_weight, payload.get("actual_payload_margin_ratio"),
                  "actual_payload_margin_ratio")
    bytes_processed = sum(path.stat().st_size for path in files.values())
    return item_rows + container_rows, bytes_processed


def _materialize_inspect(validated: ValidatedGenerationManifest, project_root: Path) -> tuple[int, int]:
    files = validated.file_paths
    mapping = project_root / "config/common/data_sources/empirical_template_level_08.yaml"
    item_result = load_csv_source(files["solver_items"], mapping)
    containers = pd.read_csv(files["solver_containers"], encoding="utf-8-sig")
    required = {"container_id", "container_type_id", "length_mm", "width_mm", "height_mm",
                "max_weight_kg", "cost", "volume_m3"}
    missing = sorted(required - set(containers.columns))
    if missing:
        raise ValueError("Materialized container source is missing columns: " + ", ".join(missing))
    if containers["container_id"].astype(str).duplicated().any():
        raise ValueError("Materialized container source contains duplicate container IDs")
    for field in ("length_mm", "width_mm", "height_mm", "max_weight_kg", "cost", "volume_m3"):
        numeric = pd.to_numeric(containers[field], errors="coerce")
        if bool(numeric.isna().any() | (numeric <= 0).any()):
            raise ValueError(f"Materialized container field {field} must be positive numeric")
    expected_items = int(validated.payload["item_count"])
    expected_containers = int(validated.payload["container_count"])
    if len(item_result.frame) != expected_items or len(containers) != expected_containers:
        raise ValueError("Materialized row counts do not match generation manifest")
    if item_result.delivery_semantics != "priority_and_stop":
        raise ValueError("Materialized item source did not retain Level 8 delivery semantics")
    bytes_processed = files["solver_items"].stat().st_size + files["solver_containers"].stat().st_size
    return len(item_result.frame) + len(containers), bytes_processed


def _inventory_scale_gate(
    validated: ValidatedGenerationManifest,
    project_root: Path,
    *,
    item_limit: int,
    candidate_limit: int,
) -> InventoryScaleGateEvidence:
    """Inspect inventory normalization and bounded lazy generation without packing."""
    if item_limit <= 0 or candidate_limit <= 0:
        return InventoryScaleGateEvidence(
            status="INVALID", runtime_seconds=0.0, peak_rss_mb=0.0, python_heap_peak_mb=0.0,
            preview_item_count=item_limit, physical_container_count=0, equivalent_type_count=0,
            lower_bound=0, hard_precheck_valid=False, candidate_count=0, candidate_signatures=(),
            subset_policy_metadata={}, issue="inventory preview item/candidate limits must be positive",
        )
    tracker = _MemoryTracker()
    tracker.start()
    started = time.perf_counter()
    try:
        files = validated.file_paths
        mapping = project_root / "config/common/data_sources/empirical_template_level_08.yaml"
        item_frame = load_csv_source(files["solver_items"], mapping).frame.head(item_limit)
        if item_frame.empty:
            raise ValueError("Generated solver_items.csv has no rows for inventory preview")
        items = [
            Item(
                item_id=str(row.id_item), length_mm=float(row.length), width_mm=float(row.width),
                height_mm=float(row.height), weight_kg=float(row.weight), level1_order=index,
            )
            for index, row in enumerate(item_frame.itertuples(index=False), start=1)
        ]
        container_frame = pd.read_csv(files["solver_containers"], encoding="utf-8-sig")
        containers = [
            Container(
                container_id=str(row.container_id), length_mm=float(row.length_mm),
                width_mm=float(row.width_mm), height_mm=float(row.height_mm),
                max_weight_kg=float(row.max_weight_kg), cost=float(row.cost),
                availability=int(row.availability), volume_m3=float(row.volume_m3),
                source={"container_type_id": str(row.container_type_id)},
            )
            for row in container_frame.itertuples(index=False)
        ]
        inventory = normalize_container_inventory(containers)
        precheck = run_hard_precheck(items, inventory)
        lower_bound = estimate_container_lower_bound(items, inventory)
        target = max(1, lower_bound.aggregate_lower_bound)
        policy = LazyRankedContainerSubsetPolicy(
            InventorySearchLimits(target, target, False),
            max_candidates_per_count=candidate_limit,
            neighborhood_width=min(32, candidate_limit),
        )
        candidates = list(policy.iter_candidates(containers, items))
        initial, peak, _, heap_peak = tracker.stop()
        return InventoryScaleGateEvidence(
            status="VALID" if precheck.valid else "INVALID",
            runtime_seconds=time.perf_counter() - started,
            peak_rss_mb=peak,
            python_heap_peak_mb=heap_peak,
            preview_item_count=len(items),
            physical_container_count=inventory.physical_container_count,
            equivalent_type_count=inventory.equivalent_type_count,
            lower_bound=lower_bound.aggregate_lower_bound,
            hard_precheck_valid=precheck.valid,
            candidate_count=len(candidates),
            candidate_signatures=tuple(
                tuple(container.container_id for container in candidate) for candidate in candidates
            ),
            subset_policy_metadata=policy.metadata(),
            issue=None if precheck.valid else "; ".join(issue.message for issue in precheck.issues),
        )
    except Exception as exc:
        _, peak, _, heap_peak = tracker.stop()
        return InventoryScaleGateEvidence(
            status="INVALID", runtime_seconds=time.perf_counter() - started,
            peak_rss_mb=peak, python_heap_peak_mb=heap_peak,
            preview_item_count=item_limit, physical_container_count=0, equivalent_type_count=0,
            lower_bound=0, hard_precheck_valid=False, candidate_count=0, candidate_signatures=(),
            subset_policy_metadata={}, issue=str(exc),
        )


def _catalog_by(path: Path, key: str) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    result = {str(row.get(key, "")): row for row in rows}
    if len(result) != len(rows) or "" in result:
        raise ValueError(f"Catalog {path.name} has empty or duplicate {key}")
    return result


class _ReaderContext:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle: Any = None

    def __enter__(self) -> csv.DictReader:
        self.handle = self.path.open(encoding="utf-8-sig", newline="")
        return csv.DictReader(self.handle)

    def __exit__(self, *_: Any) -> None:
        self.handle.close()


def _reader(path: Path) -> _ReaderContext:
    return _ReaderContext(path)


def _same_number(
    left: dict[str, Any], left_field: str, right: dict[str, Any], right_field: str, ordinal: int,
) -> None:
    left_value = _number(left.get(left_field), left_field, ordinal)
    right_value = _number(right.get(right_field), right_field, ordinal)
    if abs(left_value - right_value) > 1e-9 * max(1.0, abs(left_value), abs(right_value)):
        raise ValueError(f"Numeric field {left_field}/{right_field} mismatch at row {ordinal + 1}")


def _number(value: Any, field: str, ordinal: int) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Field {field} is not numeric at row {ordinal + 1}") from exc


def _positive_float(value: Any, field: str, ordinal: int) -> float:
    result = _number(value, field, ordinal)
    if result <= 0:
        raise ValueError(f"Field {field} must be positive at row {ordinal + 1}")
    return result


def _positive_int(value: Any, field: str, ordinal: int) -> int:
    result = _number(value, field, ordinal)
    if result <= 0 or result % 1:
        raise ValueError(f"Field {field} must be a positive integer at row {ordinal + 1}")
    return int(result)


def _assert_close(actual: float, declared: Any, field: str) -> None:
    try:
        expected = float(declared)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Manifest field {field} must be numeric") from exc
    if abs(actual - expected) > 1e-8 * max(1.0, abs(actual), abs(expected)):
        raise ValueError(f"Recomputed {field}={actual} does not match manifest value {expected}")


def _peek_manifest(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _result_payload(result: DatasetInspectionResult) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "status": result.status,
        "run_id": result.run_id,
        "profile_id": result.profile_id,
        "usage_class": result.usage_class,
        "capacity_qualification": result.capacity_qualification,
        "solver_invoked": False,
        "objective_value": None,
        "phases": {
            "provenance": asdict(result.provenance),
            "stream": asdict(result.stream) if result.stream is not None else None,
            "materialize": asdict(result.materialize) if result.materialize is not None else None,
            "inventory_scale_gate": (
                asdict(result.inventory_scale_gate)
                if result.inventory_scale_gate is not None else None
            ),
        },
        "issues": [asdict(issue) for issue in result.issues],
    }
