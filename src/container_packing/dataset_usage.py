"""Execution-intent guard for reproducibly generated synthetic datasets."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .provenance import sha256_file


SUPPORTED_GENERATOR_ID = "empirical_template_physical_instances_v1"
SUPPORTED_GENERATOR_IDS = frozenset({
    SUPPORTED_GENERATOR_ID,
    "solver_research_subset_v1",
})
SUPPORTED_SCHEMA_VERSION = "2.0"


class DatasetExecutionIntent(str, Enum):
    DATA_PREPARATION = "data_preparation"
    SOLVER_EXPERIMENT = "solver_experiment"
    BENCHMARK_ACCEPTANCE = "benchmark_acceptance"


@dataclass(frozen=True)
class DatasetUsageEvidence:
    profile_id: str
    usage_class: str
    capacity_qualification: str
    solver_acceptance_allowed: bool
    generation_manifest_path: str
    generation_manifest_checksum: str
    items_checksum: str
    containers_checksum: str
    execution_intent: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ValidatedGenerationManifest:
    manifest_path: Path
    manifest_checksum: str
    payload: dict[str, Any]
    file_paths: dict[str, Path]


def validate_generation_manifest_files(
    manifest_path: str | Path,
    *,
    file_keys: tuple[str, ...] | None = None,
) -> ValidatedGenerationManifest:
    """Validate one generation manifest and checksums for selected declared files."""
    resolved_manifest = Path(manifest_path).resolve()
    manifest = _load_manifest(resolved_manifest)
    if manifest.get("generator_id") not in SUPPORTED_GENERATOR_IDS:
        raise ValueError(
            f"Unsupported generated dataset generator_id {manifest.get('generator_id')!r}; "
            f"expected one of {sorted(SUPPORTED_GENERATOR_IDS)!r}"
        )
    if str(manifest.get("schema_version")) != SUPPORTED_SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported generated dataset schema_version {manifest.get('schema_version')!r}; "
            f"expected {SUPPORTED_SCHEMA_VERSION!r}"
        )
    files = manifest.get("files")
    checksums = manifest.get("file_sha256")
    if not isinstance(files, dict) or not isinstance(checksums, dict):
        raise ValueError(f"Generation manifest {resolved_manifest} is missing files or file_sha256 mappings")
    selected_keys = tuple(files) if file_keys is None else file_keys
    resolved_files: dict[str, Path] = {}
    for key in selected_keys:
        declared_name = files.get(key)
        declared_checksum = checksums.get(key)
        if not isinstance(declared_name, str) or not declared_name:
            raise ValueError(f"Generation manifest {resolved_manifest} does not declare files.{key}")
        path = (resolved_manifest.parent / declared_name).resolve()
        if not path.is_file():
            raise ValueError(f"Generated dataset file does not exist: {path}")
        actual_checksum = sha256_file(path)
        if not isinstance(declared_checksum, str) or actual_checksum != declared_checksum:
            raise ValueError(
                f"Generated dataset checksum mismatch for {path.name}. The file no longer matches "
                "generation_manifest.json; regenerate the profile instead of editing generated CSV manually."
            )
        resolved_files[key] = path
    return ValidatedGenerationManifest(
        manifest_path=resolved_manifest,
        manifest_checksum=sha256_file(resolved_manifest),
        payload=manifest,
        file_paths=resolved_files,
    )


def validate_dataset_usage(
    root: Path,
    config: dict[str, Any],
    intent: DatasetExecutionIntent,
) -> DatasetUsageEvidence | None:
    """Validate generated dataset provenance and its allowed execution intent."""
    root = root.resolve()
    paths = config.get("paths")
    if not isinstance(paths, dict):
        raise ValueError("Config paths must be a mapping")
    raw_items = _resolve(root, paths.get("raw_items_csv"), "paths.raw_items_csv")
    raw_containers_value = paths.get("raw_containers_csv")
    raw_containers = (
        _resolve(root, raw_containers_value, "paths.raw_containers_csv")
        if raw_containers_value else None
    )
    policy = config.get("dataset_policy")
    synthetic_root = (root / "data" / "interim" / "synthetic").resolve()
    generated_path = raw_items.is_relative_to(synthetic_root) or bool(
        raw_containers and raw_containers.is_relative_to(synthetic_root)
    )
    if policy is None and not generated_path:
        return None
    if not isinstance(policy, dict):
        raise ValueError(
            "Generated datasets require dataset_policy with generation_manifest and expected_usage_class"
        )
    manifest_value = policy.get("generation_manifest")
    if not manifest_value:
        raise ValueError("dataset_policy.generation_manifest is required for generated datasets")
    manifest_path = _resolve(root, manifest_value, "dataset_policy.generation_manifest")
    validated = validate_generation_manifest_files(
        manifest_path, file_keys=("solver_items", "solver_containers"),
    )
    manifest = validated.payload
    expected_usage = policy.get("expected_usage_class")
    if expected_usage not in {"solver_research", "data_pipeline_only"}:
        raise ValueError(
            "dataset_policy.expected_usage_class must be solver_research or data_pipeline_only"
        )
    actual_usage = str(manifest.get("usage_class", ""))
    if expected_usage != actual_usage:
        raise ValueError(
            f"Generated dataset usage mismatch: config expects {expected_usage}, manifest declares {actual_usage or 'missing'}"
        )
    if raw_containers is None:
        raise ValueError("Generated datasets require paths.raw_containers_csv")
    _verify_configured_path(raw_items, validated.file_paths["solver_items"], "solver_items")
    _verify_configured_path(raw_containers, validated.file_paths["solver_containers"], "solver_containers")
    qualification = str(manifest.get("capacity_qualification", ""))
    allowed = manifest.get("solver_acceptance_allowed")
    if not isinstance(allowed, bool):
        raise ValueError(f"Generation manifest {manifest_path} has invalid solver_acceptance_allowed")
    if intent in {DatasetExecutionIntent.SOLVER_EXPERIMENT, DatasetExecutionIntent.BENCHMARK_ACCEPTANCE}:
        if not allowed or qualification != "solver_qualified":
            profile_id = str(manifest.get("profile_id", "unknown"))
            raise ValueError(
                f"Dataset {profile_id} is {actual_usage or 'unclassified'} and cannot be used for {intent.value}. "
                "Allowed intent: data_preparation. Use a solver_research profile with "
                "capacity_qualification=solver_qualified."
            )
    return DatasetUsageEvidence(
        profile_id=str(manifest.get("profile_id", "")),
        usage_class=actual_usage,
        capacity_qualification=qualification,
        solver_acceptance_allowed=allowed,
        generation_manifest_path=_portable(root, manifest_path),
        generation_manifest_checksum=validated.manifest_checksum,
        items_checksum=sha256_file(raw_items),
        containers_checksum=sha256_file(raw_containers),
        execution_intent=intent.value,
    )


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"Cannot read generation manifest {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON generation manifest {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Generation manifest {path} must contain a JSON object")
    return payload


def _verify_configured_path(
    actual_path: Path,
    expected_path: Path,
    key: str,
) -> None:
    if actual_path.resolve() != expected_path:
        raise ValueError(
            f"Configured {key} path {actual_path} does not match generation manifest file {expected_path}"
        )


def _resolve(root: Path, value: Any, field: str) -> Path:
    if not isinstance(value, (str, Path)) or not str(value).strip():
        raise ValueError(f"{field} must be a non-empty path")
    path = Path(value)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def _portable(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())
