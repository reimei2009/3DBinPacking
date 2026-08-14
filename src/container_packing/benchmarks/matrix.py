"""Materialize a compact benchmark matrix into auditable corpus cases."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from math import ceil
from pathlib import Path
from typing import Any

import pandas as pd

from ..data_loader import load_config, merge_config
from ..instance_data import load_configured_container_catalog, select_item_rows
from ..source_adapter import load_csv_source


def _positive(value: Any, name: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return parsed


def _resolve(root: Path, value: str | Path) -> Path:
    candidate = Path(value)
    return candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()


def _capacity_lower_bound(required: float, capacities: list[float]) -> int:
    accumulated = 0.0
    for count, capacity in enumerate(sorted(capacities, reverse=True), start=1):
        accumulated += capacity
        if accumulated + 1e-12 >= required:
            return count
    return len(capacities) + 1


def _case_limits(
    source: pd.DataFrame,
    containers: pd.DataFrame,
    *,
    item_count: int,
    strategy: str,
    selection_seed: int | None,
    maximum_multiplier: float,
    maximum_extra: int,
    maximum_cap: int | None,
) -> dict[str, Any]:
    selected = select_item_rows(
        source, item_count, strategy=strategy, seed=selection_seed,
    )
    availability = (
        containers["availability"]
        if "availability" in containers
        else pd.Series(1, index=containers.index)
    )
    available = containers[
        pd.to_numeric(availability, errors="raise").eq(1)
    ].copy()
    if available.empty:
        raise ValueError("Benchmark matrix requires at least one available physical container")

    item_volume = (
        pd.to_numeric(selected["length"], errors="raise")
        * pd.to_numeric(selected["width"], errors="raise")
        * pd.to_numeric(selected["height"], errors="raise")
        / 1_000_000_000.0
    )
    item_weight = pd.to_numeric(selected["weight"], errors="raise")
    container_volume = (
        pd.to_numeric(available["length_mm"], errors="raise")
        * pd.to_numeric(available["width_mm"], errors="raise")
        * pd.to_numeric(available["height_mm"], errors="raise")
        / 1_000_000_000.0
    )
    container_payload = pd.to_numeric(available["max_weight_kg"], errors="raise")
    volume_lower_bound = _capacity_lower_bound(
        float(item_volume.sum()), container_volume.tolist(),
    )
    payload_lower_bound = _capacity_lower_bound(
        float(item_weight.sum()), container_payload.tolist(),
    )
    aggregate = max(volume_lower_bound, payload_lower_bound)
    physical_count = len(available)
    if aggregate > physical_count:
        raise ValueError(
            "Benchmark matrix case exceeds the aggregate capacity of its physical inventory"
        )
    maximum = min(
        physical_count,
        max(aggregate + maximum_extra, ceil(maximum_multiplier * aggregate)),
    )
    if maximum_cap is not None:
        maximum = min(maximum, maximum_cap)
    if maximum < aggregate:
        raise ValueError(
            "Benchmark matrix maximum_cap is lower than the aggregate lower bound"
        )
    selected_ids = selected["id_item"].astype(str).tolist()
    selected_checksum = hashlib.sha256(
        json.dumps(selected_ids, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "volume_lower_bound": volume_lower_bound,
        "payload_lower_bound": payload_lower_bound,
        "aggregate_lower_bound": aggregate,
        "physical_inventory_count": physical_count,
        "initial_used_container_count": aggregate,
        "max_used_container_count": maximum,
        "planned_selected_item_ids_checksum": selected_checksum,
    }


def expand_corpus_matrix(
    matrix: Any,
    *,
    root: Path,
    level_id: str,
    default_config: str | Path | None,
) -> list[dict[str, Any]]:
    """Expand schema 1.1 matrix syntax without changing legacy case syntax."""
    if not isinstance(matrix, dict):
        raise ValueError("Benchmark corpus matrix must be a mapping")
    configured = matrix.get("config", default_config)
    if not configured:
        raise ValueError("Benchmark corpus matrix has no config path")
    config_path = _resolve(root, str(configured))
    load_config(config_path)
    algorithms = matrix.get("algorithms")
    if not isinstance(algorithms, list) or not algorithms:
        raise ValueError("Benchmark corpus matrix must define algorithms")
    scales = matrix.get("scales")
    selections = matrix.get("selections")
    if not isinstance(scales, list) or not scales:
        raise ValueError("Benchmark corpus matrix must define scales")
    if not isinstance(selections, list) or not selections:
        raise ValueError("Benchmark corpus matrix must define selections")

    limits_policy = matrix.get("container_limits", {})
    if not isinstance(limits_policy, dict):
        raise ValueError("matrix.container_limits must be a mapping")
    multiplier = float(limits_policy.get("maximum_multiplier", 1.6))
    maximum_extra = int(limits_policy.get("maximum_extra", 2))
    maximum_cap = limits_policy.get("maximum_cap")
    maximum_cap = _positive(maximum_cap, "matrix container limit maximum_cap") if maximum_cap is not None else None
    if multiplier < 1 or maximum_extra < 0:
        raise ValueError("Benchmark matrix container limit policy is invalid")
    common_overrides = matrix.get("config_overrides", {})
    if not isinstance(common_overrides, dict):
        raise ValueError("matrix.config_overrides must be a mapping")
    prefix = str(matrix.get("case_prefix", "matrix")).strip()
    stratum = str(matrix.get("benchmark_stratum", "unclassified")).strip()
    resolved_config = merge_config(load_config(config_path), common_overrides)
    paths = resolved_config["paths"]
    raw_items = _resolve(root, paths["raw_items_csv"])
    mapping_value = paths.get("items_source_mapping")
    mapping_path = _resolve(root, mapping_value) if mapping_value else None
    source = load_csv_source(raw_items, mapping_path).frame
    containers, _ = load_configured_container_catalog(
        root, resolved_config, level_id=level_id,
    )
    cases: list[dict[str, Any]] = []
    seen_selections: dict[tuple[str, int, str], str] = {}

    for raw_scale in scales:
        if not isinstance(raw_scale, dict):
            raise ValueError("Each benchmark matrix scale must be a mapping")
        item_count = _positive(raw_scale.get("item_count"), "matrix scale item_count")
        deadline = _positive(
            raw_scale.get("time_limit_seconds"), "matrix scale time_limit_seconds",
        )
        for raw_selection in selections:
            if not isinstance(raw_selection, dict):
                raise ValueError("Each benchmark matrix selection must be a mapping")
            strategy = str(raw_selection.get("item_selection", "")).strip()
            raw_seeds = raw_selection.get("selection_seeds")
            selection_seeds = raw_seeds if isinstance(raw_seeds, list) else [None]
            if strategy == "stable_random" and not raw_seeds:
                raise ValueError("stable_random matrix selection requires selection_seeds")
            selection_id = str(raw_selection.get("selection_id", strategy)).strip()
            for seed_value in selection_seeds:
                seed = None if seed_value is None else int(seed_value)
                seed_token = f"_s{seed}" if seed is not None else ""
                case_id = f"{prefix}_{selection_id}{seed_token}_i{item_count}"
                limits = _case_limits(
                    source, containers,
                    item_count=item_count,
                    strategy=strategy,
                    selection_seed=seed,
                    maximum_multiplier=multiplier,
                    maximum_extra=maximum_extra,
                    maximum_cap=maximum_cap,
                )
                selection_key = (
                    stratum, item_count,
                    str(limits["planned_selected_item_ids_checksum"]),
                )
                previous_case = seen_selections.get(selection_key)
                if previous_case is not None:
                    raise ValueError(
                        f"Benchmark matrix cases {previous_case} and {case_id} select "
                        "the same item set; they are not independent cases"
                    )
                seen_selections[selection_key] = case_id
                overrides = merge_config(deepcopy(common_overrides), {
                    "container_search": {
                        "enabled": True,
                        "initial_used_container_count": limits["initial_used_container_count"],
                        "max_used_container_count": limits["max_used_container_count"],
                        "automatically_increase_container_count": True,
                        "time_limit_seconds": deadline,
                        "consolidation": {
                            "enabled": False,
                            "container_elimination": {"enabled": False},
                        },
                    },
                })
                cases.append({
                    "case_id": case_id,
                    "group": str(matrix.get("group", stratum)),
                    "benchmark_stratum": stratum,
                    "difficulty": str(raw_selection.get("difficulty", strategy)),
                    "item_count": item_count,
                    "container_count": limits["initial_used_container_count"],
                    "expected_outcome": str(matrix.get("expected_outcome", "feasible")),
                    "algorithms": list(algorithms),
                    "config": str(configured),
                    "description": str(raw_selection.get("description", "")),
                    "item_selection": strategy,
                    "selection_seed": seed,
                    "dataset_family": str(matrix.get("dataset_family", "unspecified")),
                    "scale_bucket": str(raw_scale.get("scale_bucket", "unspecified")),
                    "config_overrides": overrides,
                    **limits,
                })
    return cases
