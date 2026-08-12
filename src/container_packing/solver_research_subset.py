"""Materialize a bounded solver-research view from a validated generated corpus."""

from __future__ import annotations

import csv
import hashlib
import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .dataset_usage import validate_generation_manifest_files
from .provenance import sha256_file


MAXIMUM_SOLVER_RESEARCH_ITEMS = 20_000
GENERATOR_ID = "solver_research_subset_v1"
SCHEMA_VERSION = "2.0"


@dataclass(frozen=True)
class SolverResearchSubsetRequest:
    source_manifest: Path
    output_dir: Path
    profile_id: str = "level_02_solver_research_i20000_f5000_v1"
    item_count: int = MAXIMUM_SOLVER_RESEARCH_ITEMS
    minimum_volume_margin_ratio: float = 1.4
    minimum_payload_margin_ratio: float = 1.4


@dataclass(frozen=True)
class SolverResearchSubsetResult:
    output_dir: Path
    manifest_path: Path
    profile_id: str
    item_count: int
    container_count: int
    volume_margin_ratio: float
    payload_margin_ratio: float
    manifest_checksum: str


def materialize_solver_research_subset(
    request: SolverResearchSubsetRequest,
) -> SolverResearchSubsetResult:
    """Publish an immutable, deterministic prefix view only after all gates pass."""
    if not 1 <= request.item_count <= MAXIMUM_SOLVER_RESEARCH_ITEMS:
        raise ValueError(
            f"item_count must be between 1 and {MAXIMUM_SOLVER_RESEARCH_ITEMS}"
        )
    if min(request.minimum_volume_margin_ratio, request.minimum_payload_margin_ratio) < 1.0:
        raise ValueError("Solver-research capacity margins must be at least 1.0")
    if not request.profile_id.strip():
        raise ValueError("profile_id must be non-empty")

    source = validate_generation_manifest_files(
        request.source_manifest,
        file_keys=("solver_items", "solver_containers"),
    )
    output_dir = request.output_dir.resolve()
    if output_dir.exists():
        return _validated_existing_result(output_dir, request, source.manifest_checksum)
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary_dir = Path(tempfile.mkdtemp(
        prefix=f".{output_dir.name}.", dir=str(output_dir.parent),
    ))
    try:
        item_path = temporary_dir / "solver_items.csv"
        container_path = temporary_dir / "solver_containers.csv"
        container_evidence = _materialize_containers(
            source.file_paths["solver_containers"], container_path, request.profile_id,
        )
        item_evidence = _materialize_items(
            source.file_paths["solver_items"], item_path, request.profile_id,
            request.item_count, container_evidence["fit_profiles"],
        )
        volume_margin = _ratio(
            container_evidence["total_volume_m3"], item_evidence["total_volume_m3"],
        )
        payload_margin = _ratio(
            container_evidence["total_payload_kg"], item_evidence["total_weight_kg"],
        )
        if volume_margin < request.minimum_volume_margin_ratio:
            raise ValueError(
                f"Derived subset volume margin {volume_margin:.6f} is below required "
                f"{request.minimum_volume_margin_ratio:.6f}"
            )
        if payload_margin < request.minimum_payload_margin_ratio:
            raise ValueError(
                f"Derived subset payload margin {payload_margin:.6f} is below required "
                f"{request.minimum_payload_margin_ratio:.6f}"
            )
        source_payload = source.payload
        fingerprint_payload = {
            "generator_id": GENERATOR_ID,
            "profile_id": request.profile_id,
            "source_manifest_checksum": source.manifest_checksum,
            "item_count": request.item_count,
            "container_count": container_evidence["count"],
            "selection_strategy": "prefix",
            "minimum_volume_margin_ratio": request.minimum_volume_margin_ratio,
            "minimum_payload_margin_ratio": request.minimum_payload_margin_ratio,
        }
        profile_fingerprint = hashlib.sha256(json.dumps(
            fingerprint_payload, sort_keys=True, separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        manifest: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "generator_id": GENERATOR_ID,
            "profile_id": request.profile_id,
            "profile_fingerprint": profile_fingerprint,
            "usage_class": "solver_research",
            "capacity_qualification": "solver_qualified",
            "capacity_status": "capacity_feasible",
            "solver_acceptance_allowed": True,
            "recommended_use": "bounded_solver_research_after_scale_gate",
            "item_count": request.item_count,
            "container_count": container_evidence["count"],
            "item_template_count": source_payload.get("item_template_count"),
            "container_type_quantities": container_evidence["type_quantities"],
            "selection": {"strategy": "prefix", "source_row_count": request.item_count},
            "capacity_policy": {
                "minimum_volume_margin_ratio": request.minimum_volume_margin_ratio,
                "minimum_payload_margin_ratio": request.minimum_payload_margin_ratio,
                "reject_below_minimum": True,
            },
            "capacity": {
                "total_item_volume_m3": item_evidence["total_volume_m3"],
                "total_item_weight_kg": item_evidence["total_weight_kg"],
                "total_fleet_volume_m3": container_evidence["total_volume_m3"],
                "total_fleet_payload_kg": container_evidence["total_payload_kg"],
                "volume_margin_ratio": volume_margin,
                "payload_margin_ratio": payload_margin,
            },
            "actual_volume_margin_ratio": volume_margin,
            "actual_payload_margin_ratio": payload_margin,
            "required_volume_margin_ratio": request.minimum_volume_margin_ratio,
            "required_payload_margin_ratio": request.minimum_payload_margin_ratio,
            "files": {
                "solver_items": item_path.name,
                "solver_containers": container_path.name,
            },
            "file_sha256": {
                "solver_items": sha256_file(item_path),
                "solver_containers": sha256_file(container_path),
            },
            "source": {
                "profile_id": source_payload.get("profile_id"),
                "manifest_path": str(source.manifest_path),
                "manifest_sha256": source.manifest_checksum,
                "solver_items_sha256": source_payload["file_sha256"]["solver_items"],
                "solver_containers_sha256": source_payload["file_sha256"]["solver_containers"],
                "usage_class": source_payload.get("usage_class"),
            },
        }
        manifest_path = temporary_dir / "generation_manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
        temporary_dir.replace(output_dir)
    except Exception:
        shutil.rmtree(temporary_dir, ignore_errors=True)
        raise
    return _result_from_manifest(output_dir / "generation_manifest.json")


def _materialize_items(
    source: Path,
    target: Path,
    profile_id: str,
    item_count: int,
    fit_profiles: tuple[tuple[float, float, float, float], ...],
) -> dict[str, float | int]:
    required = {"id_item", "length", "width", "height", "weight"}
    seen: set[str] = set()
    total_volume = 0.0
    total_weight = 0.0
    count = 0
    with source.open("r", encoding="utf-8-sig", newline="") as input_handle, target.open(
        "w", encoding="utf-8", newline="",
    ) as output_handle:
        reader = csv.DictReader(input_handle)
        fields = list(reader.fieldnames or ())
        missing = sorted(required - set(fields))
        if missing:
            raise ValueError(f"Generated item source is missing columns: {', '.join(missing)}")
        if "synthetic_profile_id" not in fields:
            fields.append("synthetic_profile_id")
        writer = csv.DictWriter(output_handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in reader:
            if count >= item_count:
                break
            item_id = str(row["id_item"]).strip()
            if not item_id or item_id in seen:
                raise ValueError(f"Invalid or duplicate item ID at selected row {count + 1}: {item_id!r}")
            seen.add(item_id)
            length = _positive_float(row["length"], "item.length", count + 1)
            width = _positive_float(row["width"], "item.width", count + 1)
            height = _positive_float(row["height"], "item.height", count + 1)
            weight = _nonnegative_float(row["weight"], "item.weight", count + 1)
            if not any(
                length <= c_length and width <= c_width and height <= c_height and weight <= payload
                for c_length, c_width, c_height, payload in fit_profiles
            ):
                raise ValueError(f"Item {item_id} is incompatible with every container in the derived fleet")
            total_volume += length * width * height / 1_000_000_000.0
            total_weight += weight
            row["synthetic_profile_id"] = profile_id
            writer.writerow(row)
            count += 1
    if count != item_count:
        raise ValueError(f"Source provides only {count} items; requested {item_count}")
    return {"count": count, "total_volume_m3": total_volume, "total_weight_kg": total_weight}


def _materialize_containers(source: Path, target: Path, profile_id: str) -> dict[str, Any]:
    required = {
        "container_id", "container_type_id", "length_mm", "width_mm", "height_mm",
        "max_weight_kg",
    }
    seen: set[str] = set()
    type_quantities: dict[str, int] = {}
    fit_profiles: set[tuple[float, float, float, float]] = set()
    total_volume = 0.0
    total_payload = 0.0
    count = 0
    with source.open("r", encoding="utf-8-sig", newline="") as input_handle, target.open(
        "w", encoding="utf-8", newline="",
    ) as output_handle:
        reader = csv.DictReader(input_handle)
        fields = list(reader.fieldnames or ())
        missing = sorted(required - set(fields))
        if missing:
            raise ValueError(f"Generated container source is missing columns: {', '.join(missing)}")
        if "synthetic_profile_id" not in fields:
            fields.append("synthetic_profile_id")
        writer = csv.DictWriter(output_handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in reader:
            row_number = count + 1
            container_id = str(row["container_id"]).strip()
            if not container_id or container_id in seen:
                raise ValueError(f"Invalid or duplicate container ID at row {row_number}: {container_id!r}")
            seen.add(container_id)
            length = _positive_float(row["length_mm"], "container.length_mm", row_number)
            width = _positive_float(row["width_mm"], "container.width_mm", row_number)
            height = _positive_float(row["height_mm"], "container.height_mm", row_number)
            payload = _positive_float(row["max_weight_kg"], "container.max_weight_kg", row_number)
            availability = int(float(row.get("availability", 1) or 1))
            if availability <= 0:
                raise ValueError(f"Container {container_id} has non-positive availability")
            volume = length * width * height / 1_000_000_000.0
            total_volume += volume * availability
            total_payload += payload * availability
            fit_profiles.add((length, width, height, payload))
            type_id = str(row["container_type_id"]).strip()
            type_quantities[type_id] = type_quantities.get(type_id, 0) + availability
            row["synthetic_profile_id"] = profile_id
            writer.writerow(row)
            count += availability
    if count <= 0:
        raise ValueError("Derived solver-research fleet is empty")
    return {
        "count": count,
        "type_quantities": dict(sorted(type_quantities.items())),
        "fit_profiles": tuple(sorted(fit_profiles)),
        "total_volume_m3": total_volume,
        "total_payload_kg": total_payload,
    }


def _validated_existing_result(
    output_dir: Path,
    request: SolverResearchSubsetRequest,
    expected_source_checksum: str,
) -> SolverResearchSubsetResult:
    manifest_path = output_dir / "generation_manifest.json"
    validated = validate_generation_manifest_files(
        manifest_path, file_keys=("solver_items", "solver_containers"),
    )
    payload = validated.payload
    if (
        payload.get("generator_id") != GENERATOR_ID
        or payload.get("profile_id") != request.profile_id
        or int(payload.get("item_count", 0)) != request.item_count
        or payload.get("source", {}).get("manifest_sha256") != expected_source_checksum
    ):
        raise ValueError(
            f"Output directory already contains a different generated profile: {output_dir}"
        )
    return _result_from_manifest(manifest_path)


def _result_from_manifest(manifest_path: Path) -> SolverResearchSubsetResult:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    capacity = payload["capacity"]
    return SolverResearchSubsetResult(
        output_dir=manifest_path.parent,
        manifest_path=manifest_path,
        profile_id=str(payload["profile_id"]),
        item_count=int(payload["item_count"]),
        container_count=int(payload["container_count"]),
        volume_margin_ratio=float(capacity["volume_margin_ratio"]),
        payload_margin_ratio=float(capacity["payload_margin_ratio"]),
        manifest_checksum=sha256_file(manifest_path),
    )


def _positive_float(value: Any, field: str, row: int) -> float:
    parsed = _nonnegative_float(value, field, row)
    if parsed <= 0:
        raise ValueError(f"{field} must be positive at row {row}")
    return parsed


def _nonnegative_float(value: Any, field: str, row: int) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric at row {row}") from exc
    if parsed < 0:
        raise ValueError(f"{field} must be non-negative at row {row}")
    return parsed


def _ratio(capacity: float, demand: float) -> float:
    return float("inf") if demand == 0 else capacity / demand
