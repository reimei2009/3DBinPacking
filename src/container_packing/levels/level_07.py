"""Level 7 balance runtime plus frozen acceptance-fixture evidence."""

from __future__ import annotations

import csv
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
from ..schemas import Container, Item, Placement, RunResult, SolveResult
from .level_07_candidate_contract import load_runtime_candidate_contract
from .level_07_fixture_bundle import validate_level_07_fixture_bundle
from .level_07_fixture_output import write_level_07_fixture_bundle_run
from .level_07_pipeline import ALGORITHM_ID as BALANCE_ALGORITHM_ID, ALGORITHM_IDS as BALANCE_ALGORITHM_IDS
from .level_07_pipeline import GENERIC_ALGORITHM_ID, GENERIC_FFD_ALGORITHM_ID
from .level_07_pipeline import run_from_config as run_balance_from_config
from .nesting_engine import NestingRelation


ALGORITHM_ID = "level_07_fixture_validation_bundle"
FIXTURE_ID = "declared_multi_compound_chain_and_top_balance_v1"


def run(request: ExperimentRequest) -> RunResult:
    """Run a generic balance-aware solver or the frozen validation fixture."""
    if request.algorithm_id in BALANCE_ALGORITHM_IDS:
        config = load_config(request.config_path)
        if request.algorithm_id not in {GENERIC_ALGORITHM_ID, GENERIC_FFD_ALGORITHM_ID}:
            _guard_balance_request(request, config)
        return run_balance_from_config(
            request.config_path, item_count=request.item_count,
            container_count=request.container_count, level_id=request.level_id,
            algorithm_id=request.algorithm_id, environment=request.environment,
            random_seed=request.random_seed, algorithm_parameters=request.algorithm_parameters,
            config_overrides=request.config_overrides,
            item_selection_strategy=request.item_selection_strategy,
            item_selection_seed=request.item_selection_seed,
        )
    if request.algorithm_id != ALGORITHM_ID:
        raise ValueError("Level 7 exposes its validation fixture plus balance-aware Best Fit/FFD algorithms")
    started_at = perf_counter()
    root = find_project_root(__file__)
    config = load_config(request.config_path)
    _guard_request(request, config)
    manifest = prepare(request)
    items_path = _resolve_path(root, manifest["items_csv"])
    containers_path = _resolve_path(root, manifest["containers_csv"])
    items = load_items(items_path)
    containers = load_containers(containers_path)
    placements, relations = _fixture_layout(root, config, items, containers)
    bundle = validate_level_07_fixture_bundle(items, containers, placements, config, relations)
    seed = int(config["project"]["random_seed"])
    run_id = make_run_id("level_07", ALGORITHM_ID, len(items), len(containers), seed)
    output_root = _resolve_path(root, config["paths"].get("output_root", "outputs"))
    run_dir = output_root / "level_07" / "runs" / run_id
    metadata = write_level_07_fixture_bundle_run(
        run_dir, items, containers, placements, bundle, config,
        items_path=items_path, containers_path=containers_path, project_root=root,
        run_id=run_id, environment=request.environment,
        instance_id=manifest["instance_id"], random_seed=seed,
        metadata_extra={
            "item_selection_strategy": manifest["item_selection_strategy"],
            "item_selection_seed": manifest["item_selection_seed"],
            "selected_item_ids_checksum": manifest["selected_item_ids_checksum"],
            "fixture_id": FIXTURE_ID,
            "config_file": _portable_path(root, request.config_path),
            "algorithm_runtime_seconds": perf_counter() - started_at,
        },
    )
    metadata.update({
        "run_dir": _portable_path(root, run_dir),
    })
    return RunResult(
        SolveResult(
            "VALIDATION_ONLY",
            "Frozen Level 7 fixture validated; no packing solver was invoked.",
            None,
            None,
            OptimizeResult(),
        ),
        placements,
        bundle.result,
        metadata,
    )


def prepare(request: ExperimentRequest) -> dict[str, Any]:
    root = find_project_root(__file__)
    config = load_config(request.config_path)
    if request.algorithm_id in BALANCE_ALGORITHM_IDS:
        if request.algorithm_id not in {GENERIC_ALGORITHM_ID, GENERIC_FFD_ALGORITHM_ID}:
            _guard_balance_request(request, config)
        return prepare_instance(
            root, config, item_count=request.item_count, container_count=request.container_count,
            level_id="level_07", item_selection_strategy=request.item_selection_strategy,
            item_selection_seed=request.item_selection_seed,
        )
    _guard_request(request, config)
    return prepare_instance(
        root, config, item_count=request.item_count, container_count=request.container_count,
        level_id="level_07", item_selection_strategy=request.item_selection_strategy,
        item_selection_seed=request.item_selection_seed,
    )


def validate_run(run_dir: Path):
    """Independently recompute all inherited and Level 7 fixture evidence."""
    config = yaml.safe_load((run_dir / "resolved_config.yaml").read_text(encoding="utf-8"))
    items = load_items(run_dir / "input_snapshot/items.csv")
    containers = load_containers(run_dir / "input_snapshot/containers.csv")
    placements = load_placements(run_dir / "solution/placements.csv")
    algorithm_id = str(config.get("project", {}).get("algorithm_id"))
    if algorithm_id in BALANCE_ALGORITHM_IDS:
        return validate_level_07_fixture_bundle(items, containers, placements, config, None).result
    load_runtime_candidate_contract(config)
    relations = _relations_from_csv(run_dir / "solution/nesting_relations.csv")
    return validate_level_07_fixture_bundle(items, containers, placements, config, relations).result


def _guard_request(request: ExperimentRequest, config: dict[str, Any]) -> None:
    contract = load_runtime_candidate_contract(config)
    fixture = config.get("fixture")
    if not isinstance(fixture, dict):
        raise ValueError("Level 7 CLI fixture runtime requires fixture configuration")
    expected = {
        "level_id": "level_07",
        "algorithm_id": ALGORITHM_ID,
        "item_count": int(fixture["required_item_count"]),
        "container_count": int(fixture["required_container_count"]),
        "environment": str(fixture["required_environment"]),
    }
    actual = {
        "level_id": request.level_id,
        "algorithm_id": request.algorithm_id,
        "item_count": request.item_count,
        "container_count": request.container_count,
        "environment": request.environment,
    }
    for field, value in expected.items():
        if actual[field] != value:
            raise ValueError(
                f"Level 7 fixture runtime requires {field}={value!r}; got {actual[field]!r}"
            )
    if request.item_selection_strategy not in (None, fixture["required_item_selection_strategy"]):
        raise ValueError("Level 7 fixture runtime requires item_selection_strategy='prefix'")
    if request.item_selection_seed is not None:
        raise ValueError("Level 7 fixture runtime requires no item-selection seed")
    if request.random_seed not in (None, int(config["project"]["random_seed"])):
        raise ValueError("Level 7 fixture runtime requires random_seed=42")
    if request.algorithm_parameters:
        raise ValueError("Level 7 fixture runtime does not accept algorithm parameter overrides")
    if request.config_overrides:
        raise ValueError("Level 7 fixture runtime does not accept runtime config overrides")
    if fixture.get("fixture_id") != contract.fixture_id or fixture["fixture_id"] != FIXTURE_ID:
        raise ValueError("Level 7 fixture configuration does not match the frozen acceptance fixture")


def _guard_balance_request(request: ExperimentRequest, config: dict[str, Any]) -> None:
    fixture = config.get("fixture", {})
    expected = {
        "level_id": "level_07", "algorithm_id": request.algorithm_id,
        "item_count": int(fixture.get("required_item_count", -1)),
        "container_count": int(fixture.get("required_container_count", -1)),
        "environment": str(fixture.get("required_environment", "")),
    }
    actual = {
        "level_id": request.level_id, "algorithm_id": request.algorithm_id,
        "item_count": request.item_count, "container_count": request.container_count,
        "environment": request.environment,
    }
    for field, value in expected.items():
        if actual[field] != value:
            raise ValueError(f"Level 7 balance fixture requires {field}={value!r}; got {actual[field]!r}")
    if request.algorithm_id not in BALANCE_ALGORITHM_IDS:
        raise ValueError("Level 7 balance fixture requires a registered fixed Best Fit A/B algorithm")
    if request.item_selection_strategy not in (None, "prefix") or request.item_selection_seed is not None:
        raise ValueError("Level 7 balance fixture requires prefix selection with no selection seed")
    if request.random_seed not in (None, 42):
        raise ValueError("Level 7 balance fixture requires random_seed=42")
    if request.algorithm_parameters:
        raise ValueError("Level 7 balance fixture does not accept algorithm parameter overrides")
    if request.config_overrides:
        raise ValueError("Level 7 balance fixture does not accept runtime config overrides")


def _fixture_layout(
    root: Path, config: dict[str, Any], items: list[Item], containers: list[Container]
) -> tuple[list[Placement], list[NestingRelation]]:
    fixture = config["fixture"]
    layout_path = _resolve_path(root, fixture["layout_file"])
    with layout_path.open(encoding="utf-8-sig") as handle:
        layout = yaml.safe_load(handle)
    if not isinstance(layout, dict) or layout.get("fixture_id") != FIXTURE_ID:
        raise ValueError("Level 7 fixture layout has an unexpected fixture_id")
    if layout.get("orientation_code") != "XYZ":
        raise ValueError("Level 7 fixture layout requires orientation_code='XYZ'")
    item_by_id = {item.item_id: item for item in items}
    container_ids = {container.container_id for container in containers}
    raw_placements = layout.get("placements")
    if not isinstance(raw_placements, list):
        raise ValueError("Level 7 fixture layout requires placements")
    placement_ids = [str(value.get("item_id", "")) for value in raw_placements if isinstance(value, dict)]
    if len(placement_ids) != len(raw_placements) or set(placement_ids) != set(item_by_id) or len(set(placement_ids)) != len(placement_ids):
        raise ValueError("Level 7 fixture layout placements must contain every selected item exactly once")
    placements: list[Placement] = []
    for raw in raw_placements:
        if not isinstance(raw, dict):
            raise ValueError("Level 7 fixture placement must be a mapping")
        item = item_by_id[str(raw["item_id"])]
        container_id = str(raw["container_id"])
        if container_id not in container_ids:
            raise ValueError(f"Level 7 fixture placement references unknown container {container_id}")
        placements.append(Placement(
            item.item_id, container_id,
            _coordinate(raw, "x_mm"), _coordinate(raw, "y_mm"), _coordinate(raw, "z_mm"),
            item.length_mm, item.width_mm, item.height_mm, item.weight_kg, "XYZ",
        ))
    raw_relations = layout.get("relations")
    if not isinstance(raw_relations, list):
        raise ValueError("Level 7 fixture layout requires relations")
    relations = [
        NestingRelation(str(value["host_item_id"]), str(value["child_item_id"]), str(value["container_id"]))
        for value in raw_relations if isinstance(value, dict)
    ]
    if len(relations) != len(raw_relations):
        raise ValueError("Level 7 fixture relation must be a mapping")
    return placements, relations


def _relations_from_csv(path: Path) -> list[NestingRelation]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {"host_item_id", "child_item_id", "container_id"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError("Level 7 run is missing canonical nesting relation columns")
    return [NestingRelation(row["host_item_id"], row["child_item_id"], row["container_id"]) for row in rows]


def _coordinate(raw: dict[str, Any], field: str) -> float:
    try:
        value = float(raw[field])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Level 7 fixture placement requires numeric {field}") from exc
    if value < 0:
        raise ValueError(f"Level 7 fixture placement requires non-negative {field}")
    return value


def _resolve_path(root: Path, value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _portable_path(root: Path, value: Path) -> str:
    try:
        return value.relative_to(root).as_posix()
    except ValueError:
        return str(value.resolve())
