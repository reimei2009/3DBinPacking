"""CLI-only Level 8 composed validation runtime for one frozen fixture."""

from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any

import yaml
from scipy.optimize import OptimizeResult

from ..data_loader import load_config, load_containers, load_items, load_placements
from ..experiments.contracts import ExperimentRequest
from ..instance_data import prepare_instance
from ..runtime.project import find_project_root
from ..runtime.run_context import make_run_id
from ..schemas import Placement, RunResult, SolveResult, ValidationResult
from .level_07_fixture_bundle import validate_level_07_fixture_bundle
from .level_08_fixture_output import write_level_08_composed_validation_run
from .level_08_validation import validate_unloading_lifo


ALGORITHM_ID = "level_08_fixture_validation_bundle"
FIXTURE_ID = "level_08_lifo_valid_runtime_fixture_v1"


def run(request: ExperimentRequest) -> RunResult:
    """Validate one versioned Level 1--8 semantic fixture without a solver."""
    started = perf_counter()
    root = find_project_root(__file__)
    config = load_config(request.config_path)
    _guard_request(request, config)
    manifest = prepare(request)
    items_path = _resolve_path(root, manifest["items_csv"])
    containers_path = _resolve_path(root, manifest["containers_csv"])
    items = load_items(items_path)
    containers = load_containers(containers_path)
    placements = _fixture_placements(root, config, items, containers)
    inherited = validate_level_07_fixture_bundle(
        items, containers, placements, config, relations=[]
    )
    unloading = validate_unloading_lifo(
        items, placements, _unloading_rules(root, config),
        tolerance_mm=float(config.get("validation", {}).get("coordinate_tolerance_mm", 1e-6)),
    )
    issues = [*inherited.result.issues, *unloading.result.issues]
    combined = ValidationResult(not issues, issues)
    seed = int(config["project"]["random_seed"])
    run_id = make_run_id("level_08", ALGORITHM_ID, len(items), len(containers), seed)
    run_dir = _resolve_path(root, config["paths"].get("output_root", "outputs")) / "level_08" / "runs" / run_id
    metadata = write_level_08_composed_validation_run(
        run_dir, items, containers, placements, inherited, unloading, config,
        items_path=items_path, containers_path=containers_path, project_root=root,
        run_id=run_id, instance_id=manifest["instance_id"], random_seed=seed,
        runtime_seconds=perf_counter() - started,
    )
    metadata["run_dir"] = _portable_path(root, run_dir)
    return RunResult(
        SolveResult(
            "VALIDATION_ONLY" if combined.valid else "INVALID_SOLUTION",
            "Level 8 composed fixture validation; no packing solver was invoked.",
            None, None, OptimizeResult(),
        ),
        placements, combined, metadata,
    )


def prepare(request: ExperimentRequest) -> dict[str, Any]:
    root = find_project_root(__file__)
    config = load_config(request.config_path)
    _guard_request(request, config)
    return prepare_instance(
        root, config, item_count=request.item_count,
        container_count=request.container_count, level_id="level_08",
        item_selection_strategy=request.item_selection_strategy,
        item_selection_seed=request.item_selection_seed,
    )


def validate_run(run_dir: Path) -> ValidationResult:
    """Recompute inherited and unloading validation from the run snapshot."""
    config = yaml.safe_load((run_dir / "resolved_config.yaml").read_text(encoding="utf-8"))
    items = load_items(run_dir / "input_snapshot" / "items.csv")
    containers = load_containers(run_dir / "input_snapshot" / "containers.csv")
    placements = load_placements(run_dir / "solution" / "placements.csv")
    root = find_project_root(__file__)
    inherited = validate_level_07_fixture_bundle(items, containers, placements, config, relations=[])
    unloading = validate_unloading_lifo(items, placements, _unloading_rules(root, config))
    return ValidationResult(
        not [*inherited.result.issues, *unloading.result.issues],
        [*inherited.result.issues, *unloading.result.issues],
    )


def _guard_request(request: ExperimentRequest, config: dict[str, Any]) -> None:
    fixture = config.get("fixture")
    runtime = config.get("runtime_candidate")
    if not isinstance(fixture, dict) or not isinstance(runtime, dict):
        raise ValueError("Level 8 CLI runtime requires fixture and runtime_candidate configuration")
    expected = {
        "level_id": "level_08", "algorithm_id": ALGORITHM_ID,
        "item_count": int(fixture["required_item_count"]),
        "container_count": int(fixture["required_container_count"]),
        "environment": str(fixture["required_environment"]),
    }
    actual = {
        "level_id": request.level_id, "algorithm_id": request.algorithm_id,
        "item_count": request.item_count, "container_count": request.container_count,
        "environment": request.environment,
    }
    for field, expected_value in expected.items():
        if actual[field] != expected_value:
            raise ValueError(
                f"Level 8 fixture runtime requires {field}={expected_value!r}; got {actual[field]!r}"
            )
    if fixture.get("fixture_id") != FIXTURE_ID:
        raise ValueError("Level 8 fixture configuration does not match the frozen acceptance fixture")
    if request.item_selection_strategy not in (None, "prefix") or request.item_selection_seed is not None:
        raise ValueError("Level 8 fixture runtime requires prefix selection with no selection seed")
    if request.random_seed not in (None, int(config["project"]["random_seed"])):
        raise ValueError("Level 8 fixture runtime requires random_seed=42")
    if request.algorithm_parameters or request.config_overrides:
        raise ValueError("Level 8 fixture runtime does not accept runtime overrides")


def _fixture_placements(root: Path, config: dict[str, Any], items, containers) -> list[Placement]:
    path = _resolve_path(root, config["fixture"]["layout_file"])
    layout = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    if not isinstance(layout, dict) or layout.get("fixture_id") != FIXTURE_ID:
        raise ValueError("Level 8 fixture layout has an unexpected fixture_id")
    if layout.get("orientation_code") != "XYZ":
        raise ValueError("Level 8 fixture layout requires orientation_code='XYZ'")
    item_by_id = {item.item_id: item for item in items}
    container_ids = {container.container_id for container in containers}
    raw = layout.get("placements")
    if not isinstance(raw, list) or len(raw) != len(items):
        raise ValueError("Level 8 fixture layout must place every selected item exactly once")
    placements: list[Placement] = []
    for value in raw:
        if not isinstance(value, dict):
            raise ValueError("Level 8 fixture placement must be a mapping")
        item_id = str(value.get("item_id", ""))
        container_id = str(value.get("container_id", ""))
        if item_id not in item_by_id or container_id not in container_ids:
            raise ValueError("Level 8 fixture placement references an unknown item or container")
        item = item_by_id[item_id]
        placements.append(Placement(
            item_id, container_id, *_coordinates(value),
            item.length_mm, item.width_mm, item.height_mm, item.weight_kg, "XYZ",
        ))
    if {value.item_id for value in placements} != set(item_by_id):
        raise ValueError("Level 8 fixture layout must contain every selected item exactly once")
    return placements


def _unloading_rules(root: Path, config: dict[str, Any]) -> dict[str, Any]:
    value = config.get("unloading", {})
    path = value.get("rules_file") if isinstance(value, dict) else None
    if not path:
        raise ValueError("Level 8 runtime requires unloading.rules_file")
    return load_config(_resolve_path(root, path))


def _coordinates(value: dict[str, Any]) -> tuple[float, float, float]:
    try:
        coordinates = tuple(float(value[name]) for name in ("x_mm", "y_mm", "z_mm"))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Level 8 fixture placement requires numeric x_mm, y_mm, z_mm") from exc
    if any(number < 0 for number in coordinates):
        raise ValueError("Level 8 fixture placement coordinates must be non-negative")
    return coordinates


def _resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _portable_path(root: Path, value: Path) -> str:
    try:
        return value.relative_to(root).as_posix()
    except ValueError:
        return str(value.resolve())
