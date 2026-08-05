"""Reproducible large-scale physical instance generation from source catalogs."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from random import Random
from typing import Any, TextIO

import pandas as pd

from .data_loader import load_config
from .provenance import sha256_file
from .runtime.project import find_project_root


ITEM_TEMPLATE_FIELDS = (
    "length", "width", "height", "weight", "nesting_height",
    "stackability_code", "forced_orientation", "max_stackability",
)
ITEM_SOURCE_COLUMNS = {"id_item", *ITEM_TEMPLATE_FIELDS}
CONTAINER_SOURCE_COLUMNS = {
    "container_id", "length_mm", "width_mm", "height_mm",
    "max_weight_kg", "cost", "availability", "volume_m3",
}


@dataclass(frozen=True)
class LargeSyntheticProfile:
    schema_version: str
    profile_id: str
    seed: int
    root: Path
    items_file: Path
    containers_file: Path
    container_types: tuple[str, ...]
    item_count: int
    sampling: str
    weight_noise_percent: float
    container_quantities: dict[str, int]
    delivery_stop_count: int
    delivery_assignment: str
    output_dir: Path
    allow_intentionally_infeasible: bool
    usage_class: str
    minimum_volume_margin_ratio: float
    minimum_payload_margin_ratio: float
    reject_below_minimum: bool

    @property
    def container_count(self) -> int:
        return sum(self.container_quantities.values())


def load_large_synthetic_profile(
    path: str | Path, *, root: Path | None = None,
) -> LargeSyntheticProfile:
    """Load and validate one schema-v2 large synthetic generation profile."""
    root = (root or find_project_root(__file__)).resolve()
    config_path = Path(path)
    if not config_path.is_absolute():
        config_path = root / config_path
    config = load_config(config_path)
    schema_version = _text(config.get("schema_version"), "schema_version")
    if schema_version != "2.0":
        raise ValueError(f"schema_version must be '2.0'; got {schema_version!r}")
    source = _mapping(config.get("source"), "source")
    item_population = _mapping(config.get("item_population"), "item_population")
    fleet = _mapping(config.get("container_fleet"), "container_fleet")
    enrichment = _mapping(config.get("level_08_enrichment"), "level_08_enrichment")
    output = _mapping(config.get("output"), "output")
    usage_class = _text(config.get("usage_class"), "usage_class")
    if usage_class not in {"solver_research", "data_pipeline_only"}:
        raise ValueError("usage_class must be solver_research or data_pipeline_only")
    capacity_policy = _mapping(config.get("capacity_policy"), "capacity_policy")
    minimum_volume_margin = _minimum_margin(
        capacity_policy.get("minimum_volume_margin_ratio"),
        "capacity_policy.minimum_volume_margin_ratio",
    )
    minimum_payload_margin = _minimum_margin(
        capacity_policy.get("minimum_payload_margin_ratio"),
        "capacity_policy.minimum_payload_margin_ratio",
    )
    container_types_raw = source.get("container_types")
    if not isinstance(container_types_raw, list) or not container_types_raw:
        raise ValueError("source.container_types must be a non-empty list")
    container_types = tuple(_text(value, "source.container_types[]") for value in container_types_raw)
    if len(set(container_types)) != len(container_types):
        raise ValueError("source.container_types must not contain duplicates")
    quantities_raw = _mapping(fleet.get("quantities"), "container_fleet.quantities")
    unknown_types = sorted(set(quantities_raw) - set(container_types))
    if unknown_types:
        raise ValueError("container_fleet.quantities contains unknown type(s): " + ", ".join(unknown_types))
    quantities = {type_id: _non_negative_int(quantities_raw.get(type_id, 0), f"quantity {type_id}")
                  for type_id in container_types}
    if sum(quantities.values()) <= 0:
        raise ValueError("container_fleet.quantities must create at least one container")
    sampling = _text(item_population.get("sampling"), "item_population.sampling")
    if sampling != "empirical_template_frequency":
        raise ValueError("item_population.sampling currently supports only empirical_template_frequency")
    assignment = _text(enrichment.get("assignment"), "level_08_enrichment.assignment")
    if assignment != "balanced_seeded":
        raise ValueError("level_08_enrichment.assignment currently supports only balanced_seeded")
    stop_count = _positive_int(enrichment.get("delivery_stop_count"), "delivery_stop_count")
    item_count = _positive_int(item_population.get("count"), "item_population.count")
    if stop_count > item_count:
        raise ValueError("delivery_stop_count must not exceed item count")
    noise = _non_negative_float(item_population.get("weight_noise_percent", 0), "weight_noise_percent")
    if noise > 100:
        raise ValueError("weight_noise_percent must not exceed 100")
    return LargeSyntheticProfile(
        schema_version=schema_version,
        profile_id=_text(config.get("profile_id"), "profile_id"),
        seed=_non_negative_int(config.get("seed"), "seed"),
        root=root,
        items_file=_root_path(root, source.get("items_file"), "source.items_file"),
        containers_file=_root_path(root, source.get("containers_file"), "source.containers_file"),
        container_types=container_types,
        item_count=item_count,
        sampling=sampling,
        weight_noise_percent=noise,
        container_quantities=quantities,
        delivery_stop_count=stop_count,
        delivery_assignment=assignment,
        output_dir=_root_path(root, output.get("directory"), "output.directory"),
        allow_intentionally_infeasible=_boolean(
            config.get("allow_intentionally_infeasible", False), "allow_intentionally_infeasible"
        ),
        usage_class=usage_class,
        minimum_volume_margin_ratio=minimum_volume_margin,
        minimum_payload_margin_ratio=minimum_payload_margin,
        reject_below_minimum=_boolean(
            capacity_policy.get("reject_below_minimum"), "capacity_policy.reject_below_minimum"
        ),
    )


def generate_large_synthetic_instances(
    profile: LargeSyntheticProfile, *, overwrite: bool = False,
) -> dict[str, Any]:
    """Generate normalized catalogs, physical instances and Level-8-ready CSVs."""
    item_source = _read_source(profile.items_file, ITEM_SOURCE_COLUMNS, "item")
    container_source = _read_source(profile.containers_file, CONTAINER_SOURCE_COLUMNS, "container")
    template_catalog = _build_item_template_catalog(item_source)
    container_catalog = _build_container_type_catalog(container_source, profile.container_types)
    paths = _output_paths(profile.output_dir)
    existing = [str(path) for path in paths.values() if path.exists()]
    if existing and not overwrite:
        raise FileExistsError("Refusing to overwrite generated synthetic data; use --overwrite: " + ", ".join(existing))
    profile.output_dir.mkdir(parents=True, exist_ok=True)

    temporary = {name: path.with_suffix(path.suffix + ".tmp") for name, path in paths.items() if name != "manifest"}
    for path in temporary.values():
        path.unlink(missing_ok=True)
    template_counts = {str(row.item_template_id): int(row.source_row_count)
                       for row in template_catalog.itertuples(index=False)}
    rng = Random(profile.seed)
    delivery_rng = Random(profile.seed ^ 0x4C385F21)
    priority_pool = [1 + index % profile.delivery_stop_count for index in range(profile.item_count)]
    delivery_rng.shuffle(priority_pool)
    total_item_volume_m3 = 0.0
    total_item_weight_kg = 0.0
    sampled_template_counts = {template_id: 0 for template_id in template_counts}

    try:
        _write_frame_temp(template_catalog, temporary["item_templates"])
        _write_frame_temp(container_catalog, temporary["container_types"])
        container_summary = _write_container_instances(profile, container_catalog, temporary)
        item_handles = _open_item_writers(temporary)
        try:
            template_rows = template_catalog.to_dict(orient="records")
            weights = [template_counts[str(row["item_template_id"])] for row in template_rows]
            for ordinal in range(1, profile.item_count + 1):
                template = rng.choices(template_rows, weights=weights, k=1)[0]
                template_id = str(template["item_template_id"])
                sampled_template_counts[template_id] += 1
                base_weight = float(template["base_weight_kg"])
                actual_weight = _sample_weight(base_weight, profile.weight_noise_percent, rng)
                priority = priority_pool[ordinal - 1]
                item_id = f"ITEM-{ordinal:09d}"
                stop_id = f"STOP-{priority:04d}"
                total_item_volume_m3 += (
                    float(template["length_mm"]) * float(template["width_mm"]) * float(template["height_mm"])
                    / 1_000_000_000.0
                )
                total_item_weight_kg += actual_weight
                _write_item_rows(item_handles, profile, ordinal, item_id, template_id, template, actual_weight,
                                 priority, stop_id)
        finally:
            for handle, _ in item_handles.values():
                handle.close()
        capacity = {
            "total_item_volume_m3": total_item_volume_m3,
            "total_item_weight_kg": total_item_weight_kg,
            **container_summary,
        }
        capacity["volume_margin_ratio"] = (
            container_summary["total_fleet_volume_m3"] / total_item_volume_m3 if total_item_volume_m3 else None
        )
        capacity["payload_margin_ratio"] = (
            container_summary["total_fleet_payload_kg"] / total_item_weight_kg if total_item_weight_kg else None
        )
        capacity_feasible = (
            total_item_volume_m3 <= container_summary["total_fleet_volume_m3"] + 1e-9
            and total_item_weight_kg <= container_summary["total_fleet_payload_kg"] + 1e-9
        )
        if not capacity_feasible and not profile.allow_intentionally_infeasible:
            raise ValueError(
                "Generated item population exceeds aggregate fleet capacity; increase container quantities or set "
                "allow_intentionally_infeasible: true explicitly"
            )
        qualification = _qualify_capacity(profile, capacity, capacity_feasible)
        if qualification["rejected"]:
            raise ValueError(
                "Generated population does not meet the declared capacity policy: "
                f"volume margin {capacity['volume_margin_ratio']:.6f} "
                f"(required {profile.minimum_volume_margin_ratio:.6f}), payload margin "
                f"{capacity['payload_margin_ratio']:.6f} "
                f"(required {profile.minimum_payload_margin_ratio:.6f})"
            )
        for name, temporary_path in temporary.items():
            os.replace(temporary_path, paths[name])
        manifest = _manifest(
            profile, paths, template_catalog, sampled_template_counts, capacity, capacity_feasible, qualification,
        )
        _atomic_json(manifest, paths["manifest"])
        return {**manifest, "manifest_path": str(paths["manifest"]),
                "solver_items_path": str(paths["solver_items"]),
                "solver_containers_path": str(paths["solver_containers"])}
    except Exception:
        for path in temporary.values():
            path.unlink(missing_ok=True)
        raise


def _build_item_template_catalog(source: pd.DataFrame) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    normalized = source.copy()
    for column in ("length", "width", "height", "weight", "nesting_height", "max_stackability"):
        normalized[column] = pd.to_numeric(normalized[column], errors="raise")
    if bool((normalized[["length", "width", "height", "weight"]] <= 0).any().any()):
        raise ValueError("Item source dimensions and weight must be positive")
    for values, group in normalized.groupby(list(ITEM_TEMPLATE_FIELDS), dropna=False, sort=True):
        canonical = dict(zip(ITEM_TEMPLATE_FIELDS, values, strict=True))
        digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        source_ids = sorted(str(value) for value in group["id_item"])
        records.append({
            "item_template_id": f"SKU-{digest[:16].upper()}",
            "representative_source_item_id": source_ids[0],
            "length_mm": float(canonical["length"]),
            "width_mm": float(canonical["width"]),
            "height_mm": float(canonical["height"]),
            "base_weight_kg": float(canonical["weight"]),
            "nesting_height_mm": float(canonical["nesting_height"]),
            "stackability_code": str(canonical["stackability_code"]),
            "forced_orientation": str(canonical["forced_orientation"]),
            "max_stackability": int(canonical["max_stackability"]),
            "source_row_count": len(group),
            "source_item_ids_sha256": hashlib.sha256("\n".join(source_ids).encode("utf-8")).hexdigest(),
        })
    result = pd.DataFrame(records).sort_values("item_template_id").reset_index(drop=True)
    if result["item_template_id"].duplicated().any():
        raise ValueError("Stable item template hash collision detected")
    return result


def _build_container_type_catalog(source: pd.DataFrame, type_ids: tuple[str, ...]) -> pd.DataFrame:
    selected = source[source["container_id"].astype(str).isin(type_ids)].copy()
    missing = sorted(set(type_ids) - set(selected["container_id"].astype(str)))
    if missing:
        raise ValueError("Container source is missing requested type(s): " + ", ".join(missing))
    selected = selected.set_index(selected["container_id"].astype(str)).loc[list(type_ids)].reset_index(drop=True)
    return pd.DataFrame({
        "container_type_id": selected["container_id"].astype(str),
        "length_mm": pd.to_numeric(selected["length_mm"], errors="raise"),
        "width_mm": pd.to_numeric(selected["width_mm"], errors="raise"),
        "height_mm": pd.to_numeric(selected["height_mm"], errors="raise"),
        "max_weight_kg": pd.to_numeric(selected["max_weight_kg"], errors="raise"),
        "cost": pd.to_numeric(selected["cost"], errors="raise"),
        "volume_m3": pd.to_numeric(selected["volume_m3"], errors="raise"),
        "source_container_id": selected["container_id"].astype(str),
    })


def _write_container_instances(
    profile: LargeSyntheticProfile, catalog: pd.DataFrame, temporary: dict[str, Path],
) -> dict[str, float]:
    type_lookup = {str(row.container_type_id): row for row in catalog.itertuples(index=False)}
    fields = ["container_id", "container_type_id", "length_mm", "width_mm", "height_mm", "max_weight_kg",
              "availability", "cost", "volume_m3", "synthetic_profile_id", "data_status"]
    instance_tmp = temporary["container_instances"]
    solver_tmp = temporary["solver_containers"]
    total_volume = 0.0
    total_payload = 0.0
    with instance_tmp.open("w", encoding="utf-8-sig", newline="") as instance_handle, \
            solver_tmp.open("w", encoding="utf-8-sig", newline="") as solver_handle:
        instance_writer = csv.DictWriter(instance_handle, fieldnames=fields)
        solver_writer = csv.DictWriter(solver_handle, fieldnames=fields)
        instance_writer.writeheader()
        solver_writer.writeheader()
        for type_id in profile.container_types:
            source = type_lookup[type_id]
            for ordinal in range(1, profile.container_quantities[type_id] + 1):
                row = {
                    "container_id": f"CONT-{type_id}-{ordinal:06d}", "container_type_id": type_id,
                    "length_mm": source.length_mm, "width_mm": source.width_mm, "height_mm": source.height_mm,
                    "max_weight_kg": source.max_weight_kg, "availability": 1, "cost": source.cost,
                    "volume_m3": source.volume_m3, "synthetic_profile_id": profile.profile_id,
                    "data_status": "empirical_template_physical_instance_v1",
                }
                instance_writer.writerow(row)
                solver_writer.writerow(row)
                total_volume += float(source.volume_m3)
                total_payload += float(source.max_weight_kg)
    return {"total_fleet_volume_m3": total_volume, "total_fleet_payload_kg": total_payload}


def _open_item_writers(temporary: dict[str, Path]) -> dict[str, tuple[TextIO, csv.DictWriter]]:
    fields = {
        "item_instances": ["item_id", "item_template_id", "actual_weight_kg", "instance_ordinal",
                           "synthetic_profile_id"],
        "delivery": ["item_id", "delivery_priority", "delivery_stop_id", "delivery_data_source"],
        "solver_items": ["id_item", "item_template_id", "length", "width", "height", "weight",
                         "nesting_height", "stackability_code", "forced_orientation", "max_stackability",
                         "delivery_priority", "delivery_stop_id", "delivery_data_source",
                         "synthetic_profile_id"],
    }
    result: dict[str, tuple[TextIO, csv.DictWriter]] = {}
    for name, fieldnames in fields.items():
        handle = temporary[name].open("w", encoding="utf-8-sig", newline="")
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        result[name] = (handle, writer)
    return result


def _write_item_rows(
    handles: dict[str, tuple[TextIO, csv.DictWriter]], profile: LargeSyntheticProfile, ordinal: int,
    item_id: str, template_id: str, template: dict[str, Any], actual_weight: float,
    priority: int, stop_id: str,
) -> None:
    handles["item_instances"][1].writerow({
        "item_id": item_id, "item_template_id": template_id, "actual_weight_kg": actual_weight,
        "instance_ordinal": ordinal, "synthetic_profile_id": profile.profile_id,
    })
    handles["delivery"][1].writerow({
        "item_id": item_id, "delivery_priority": priority, "delivery_stop_id": stop_id,
        "delivery_data_source": "empirical_template_level_08_enrichment_v1",
    })
    handles["solver_items"][1].writerow({
        "id_item": item_id, "item_template_id": template_id,
        "length": template["length_mm"], "width": template["width_mm"], "height": template["height_mm"],
        "weight": actual_weight, "nesting_height": template["nesting_height_mm"],
        "stackability_code": template["stackability_code"], "forced_orientation": template["forced_orientation"],
        "max_stackability": template["max_stackability"], "delivery_priority": priority,
        "delivery_stop_id": stop_id, "delivery_data_source": "empirical_template_level_08_enrichment_v1",
        "synthetic_profile_id": profile.profile_id,
    })


def _manifest(
    profile: LargeSyntheticProfile, paths: dict[str, Path], templates: pd.DataFrame,
    sampled_counts: dict[str, int], capacity: dict[str, float], capacity_feasible: bool,
    qualification: dict[str, Any],
) -> dict[str, Any]:
    file_checksums = {name: sha256_file(path) for name, path in paths.items() if name != "manifest"}
    payload = {
        "generator_id": "empirical_template_physical_instances_v1",
        "schema_version": profile.schema_version,
        "profile_id": profile.profile_id,
        "seed": profile.seed,
        "source_items_file": str(profile.items_file.relative_to(profile.root)),
        "source_items_sha256": sha256_file(profile.items_file),
        "source_containers_file": str(profile.containers_file.relative_to(profile.root)),
        "source_containers_sha256": sha256_file(profile.containers_file),
        "item_count": profile.item_count,
        "item_template_count": len(templates),
        "container_count": profile.container_count,
        "container_type_quantities": profile.container_quantities,
        "delivery_stop_count": profile.delivery_stop_count,
        "sampling": profile.sampling,
        "weight_noise_percent": profile.weight_noise_percent,
        "usage_class": profile.usage_class,
        "capacity_policy": {
            "minimum_volume_margin_ratio": profile.minimum_volume_margin_ratio,
            "minimum_payload_margin_ratio": profile.minimum_payload_margin_ratio,
            "reject_below_minimum": profile.reject_below_minimum,
        },
        "sampled_template_distribution": {key: value for key, value in sampled_counts.items() if value},
        "capacity": capacity,
        "capacity_status": "capacity_feasible" if capacity_feasible else "intentionally_infeasible",
        "capacity_qualification": qualification["capacity_qualification"],
        "solver_acceptance_allowed": qualification["solver_acceptance_allowed"],
        "recommended_use": qualification["recommended_use"],
        "required_volume_margin_ratio": profile.minimum_volume_margin_ratio,
        "required_payload_margin_ratio": profile.minimum_payload_margin_ratio,
        "actual_volume_margin_ratio": capacity["volume_margin_ratio"],
        "actual_payload_margin_ratio": capacity["payload_margin_ratio"],
        "files": {name: path.name for name, path in paths.items() if name != "manifest"},
        "file_sha256": file_checksums,
    }
    payload["profile_fingerprint"] = hashlib.sha256(
        json.dumps({key: payload[key] for key in (
            "schema_version", "profile_id", "seed", "source_items_sha256", "source_containers_sha256",
            "item_count", "container_type_quantities", "delivery_stop_count", "sampling",
            "weight_noise_percent", "usage_class", "capacity_policy",
        )}, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return payload


def _qualify_capacity(
    profile: LargeSyntheticProfile, capacity: dict[str, float], aggregate_feasible: bool,
) -> dict[str, Any]:
    if not aggregate_feasible:
        return {
            "capacity_qualification": "intentionally_infeasible",
            "solver_acceptance_allowed": False,
            "recommended_use": "negative_capacity_fixture_only",
            "rejected": False,
        }
    meets_declared_policy = (
        capacity["volume_margin_ratio"] >= profile.minimum_volume_margin_ratio
        and capacity["payload_margin_ratio"] >= profile.minimum_payload_margin_ratio
    )
    if profile.usage_class == "solver_research" and meets_declared_policy:
        return {
            "capacity_qualification": "solver_qualified",
            "solver_acceptance_allowed": True,
            "recommended_use": "solver_research_and_benchmark",
            "rejected": False,
        }
    if profile.usage_class == "solver_research" and profile.reject_below_minimum:
        return {
            "capacity_qualification": "rejected",
            "solver_acceptance_allowed": False,
            "recommended_use": "none",
            "rejected": True,
        }
    return {
        "capacity_qualification": "pipeline_qualified",
        "solver_acceptance_allowed": False,
        "recommended_use": "data_pipeline_testing_only",
        "rejected": profile.reject_below_minimum and not meets_declared_policy,
    }


def _output_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "item_templates": output_dir / "item_template_catalog.csv",
        "item_instances": output_dir / "item_instances.csv",
        "container_types": output_dir / "container_type_catalog.csv",
        "container_instances": output_dir / "container_instances.csv",
        "delivery": output_dir / "delivery_enrichment.csv",
        "solver_items": output_dir / "solver_items.csv",
        "solver_containers": output_dir / "solver_containers.csv",
        "manifest": output_dir / "generation_manifest.json",
    }


def _read_source(path: Path, required: set[str], label: str) -> pd.DataFrame:
    try:
        frame = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    except (OSError, pd.errors.ParserError) as exc:
        raise ValueError(f"Cannot read {label} source {path}: {exc}") from exc
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{label.title()} source {path} is missing columns: {', '.join(missing)}")
    return frame


def _write_frame_temp(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, encoding="utf-8-sig")


def _atomic_json(payload: dict[str, Any], path: Path) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _sample_weight(base: float, noise_percent: float, rng: Random) -> float:
    if noise_percent == 0:
        return base
    ratio = noise_percent / 100.0
    return round(base * rng.uniform(1.0 - ratio, 1.0 + ratio), 6)


def _mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be a mapping")
    return value


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _root_path(root: Path, value: Any, field: str) -> Path:
    path = Path(_text(value, field))
    return path if path.is_absolute() else root / path


def _non_negative_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an integer") from exc
    if result < 0:
        raise ValueError(f"{field} must be non-negative")
    return result


def _positive_int(value: Any, field: str) -> int:
    result = _non_negative_int(value, field)
    if result == 0:
        raise ValueError(f"{field} must be positive")
    return result


def _non_negative_float(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if result < 0:
        raise ValueError(f"{field} must be non-negative")
    return result


def _minimum_margin(value: Any, field: str) -> float:
    result = _non_negative_float(value, field)
    if result < 1.0:
        raise ValueError(f"{field} must be at least 1.0")
    return result


def _boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be boolean")
    return value
