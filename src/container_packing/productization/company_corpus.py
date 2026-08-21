"""Governed company-like shadow corpus built from declared synthetic assumptions."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
from typing import Any

import yaml

from ..provenance import sha256_file
from ..runtime.project import find_project_root
from ..synthetic_instances import (
    generate_large_synthetic_instances,
    load_large_synthetic_profile,
)


_FIELD_STATUSES = {"used", "preserved", "transformed", "unsupported"}
_ALGORITHMS = {
    "extreme_point_best_fit", "extreme_point_ffd", "maximal_space_best_fit",
}


@dataclass(frozen=True)
class CompanyCorpusContract:
    schema_version: str
    corpus_id: str
    evidence_class: str
    generation_profile: Path
    calibration_source: str
    field_governance: dict[str, dict[str, str]]
    algorithms: tuple[str, ...]
    scales: tuple[int, ...]
    case_families: tuple[str, ...]
    slo: dict[str, Any]
    caching_reconsideration: dict[str, float]
    safety_statement_vi: str
    safety_statement_en: str
    root: Path
    contract_path: Path


def load_company_corpus_contract(
    path: str | Path, *, root: Path | None = None,
) -> CompanyCorpusContract:
    """Load a shadow-only contract and reject unsupported production claims."""
    project_root = (root or find_project_root(__file__)).resolve()
    contract_path = _resolve(project_root, path)
    try:
        payload = yaml.safe_load(contract_path.read_text(encoding="utf-8-sig"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"Cannot read company-like corpus contract {contract_path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Company-like corpus contract must contain a mapping")
    if str(payload.get("schema_version")) != "1.0":
        raise ValueError("Company-like corpus schema_version must be '1.0'")
    evidence_class = _text(payload.get("evidence_class"), "evidence_class")
    if evidence_class not in {"synthetic_calibrated_shadow", "company_provided_shadow"}:
        raise ValueError(
            "evidence_class must be synthetic_calibrated_shadow or company_provided_shadow"
        )
    source = _mapping(payload.get("source"), "source")
    generation_profile = _resolve(
        project_root, _text(source.get("generation_profile"), "source.generation_profile")
    )
    if not generation_profile.is_file():
        raise ValueError(f"Generation profile does not exist: {generation_profile}")
    calibration_source = _text(
        source.get("calibration_source"), "source.calibration_source",
    )
    governance = _mapping(payload.get("field_governance"), "field_governance")
    required = {
        "dimensions", "weight", "container_mix", "container_cost",
        "load_bearing", "safety_clearance", "measurement_error",
    }
    missing = required - set(governance)
    if missing:
        raise ValueError("field_governance is missing: " + ", ".join(sorted(missing)))
    normalized_governance: dict[str, dict[str, str]] = {}
    for field, raw in governance.items():
        entry = _mapping(raw, f"field_governance.{field}")
        status = _text(entry.get("status"), f"field_governance.{field}.status")
        if status not in _FIELD_STATUSES:
            raise ValueError(
                f"field_governance.{field}.status must be one of {sorted(_FIELD_STATUSES)}"
            )
        normalized_governance[str(field)] = {
            "status": status,
            "provenance": _text(
                entry.get("provenance"), f"field_governance.{field}.provenance",
            ),
        }
    benchmark = _mapping(payload.get("benchmark"), "benchmark")
    algorithms = tuple(str(value) for value in _list(benchmark.get("algorithms"), "benchmark.algorithms"))
    if set(algorithms) != _ALGORITHMS or len(algorithms) != len(_ALGORITHMS):
        raise ValueError("Company shadow benchmark must use Best Fit, FFD and MES exactly once")
    scales = tuple(_positive_int(value, "benchmark.scales[]") for value in _list(benchmark.get("scales"), "benchmark.scales"))
    if len(set(scales)) != len(scales):
        raise ValueError("benchmark.scales must not contain duplicates")
    families = tuple(str(value) for value in _list(benchmark.get("case_families"), "benchmark.case_families"))
    if len(set(families)) != len(families):
        raise ValueError("benchmark.case_families must not contain duplicates")
    slo = _mapping(payload.get("slo"), "slo")
    _validate_slo(slo, scales)
    cache = _mapping(payload.get("caching_reconsideration"), "caching_reconsideration")
    caching = {
        "minimum_profile_share": _ratio(cache.get("minimum_profile_share"), "minimum_profile_share"),
        "minimum_expected_hit_rate": _ratio(cache.get("minimum_expected_hit_rate"), "minimum_expected_hit_rate"),
        "minimum_projected_wall_improvement": _ratio(
            cache.get("minimum_projected_wall_improvement"), "minimum_projected_wall_improvement",
        ),
    }
    statements = _mapping(payload.get("safety_statement"), "safety_statement")
    return CompanyCorpusContract(
        schema_version="1.0",
        corpus_id=_text(payload.get("corpus_id"), "corpus_id"),
        evidence_class=evidence_class,
        generation_profile=generation_profile,
        calibration_source=calibration_source,
        field_governance=normalized_governance,
        algorithms=algorithms,
        scales=scales,
        case_families=families,
        slo=slo,
        caching_reconsideration=caching,
        safety_statement_vi=_text(statements.get("vi"), "safety_statement.vi"),
        safety_statement_en=_text(statements.get("en"), "safety_statement.en"),
        root=project_root,
        contract_path=contract_path,
    )


def prepare_company_shadow_corpus(
    contract: CompanyCorpusContract,
    *,
    output_dir_override: Path | None = None,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Generate the declared population and publish a shadow-only sidecar manifest."""
    profile = load_large_synthetic_profile(contract.generation_profile, root=contract.root)
    if output_dir_override is not None:
        profile = replace(profile, output_dir=output_dir_override.resolve())
    result = generate_large_synthetic_instances(profile, overwrite=overwrite)
    output_dir = Path(result["manifest_path"]).parent
    generation_manifest = Path(result["manifest_path"])
    contract_path = contract.contract_path
    sidecar = {
        "schema_version": "1.0",
        "corpus_id": contract.corpus_id,
        "evidence_class": contract.evidence_class,
        "production_evidence": False,
        "shadow_evaluation_only": True,
        "profile_id": result["profile_id"],
        "item_count": result["item_count"],
        "container_count": result["container_count"],
        "generation_manifest": str(generation_manifest),
        "generation_manifest_sha256": sha256_file(generation_manifest),
        "contract_file": str(contract_path),
        "contract_sha256": sha256_file(contract_path),
        "calibration_source": contract.calibration_source,
        "field_governance": contract.field_governance,
        "algorithms": list(contract.algorithms),
        "scales": list(contract.scales),
        "case_families": list(contract.case_families),
        "safety_statement": {
            "vi": contract.safety_statement_vi,
            "en": contract.safety_statement_en,
        },
    }
    destination = output_dir / "company_shadow_manifest.json"
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(sidecar, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    os.replace(temporary, destination)
    return {**sidecar, "company_shadow_manifest": str(destination)}


def _resolve(root: Path, value: str | Path) -> Path:
    candidate = Path(value)
    return candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return dict(value)


def _list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{name} must be a non-empty list")
    return value


def _text(value: Any, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} must be a non-empty string")
    return text


def _positive_int(value: Any, name: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise ValueError(f"{name} must be positive")
    return parsed


def _ratio(value: Any, name: str) -> float:
    parsed = float(value)
    if not 0 < parsed <= 1:
        raise ValueError(f"caching_reconsideration.{name} must be in (0, 1]")
    return parsed


def _validate_slo(slo: dict[str, Any], scales: tuple[int, ...]) -> None:
    for name in ("required_valid_rate", "maximum_timeout_rate", "maximum_invalid_rate"):
        value = float(slo.get(name, -1))
        if not 0 <= value <= 1:
            raise ValueError(f"slo.{name} must be in [0, 1]")
    runtime_limits = _mapping(slo.get("runtime_p95_seconds"), "slo.runtime_p95_seconds")
    if {int(value) for value in runtime_limits} != set(scales):
        raise ValueError("slo.runtime_p95_seconds must declare every benchmark scale exactly")
    for scale, value in runtime_limits.items():
        if float(value) <= 0:
            raise ValueError(f"slo.runtime_p95_seconds.{scale} must be positive")
    for name in (
        "maximum_peak_rss_bytes", "ui_response_p95_seconds",
        "minimum_runtime_samples_per_scale",
    ):
        if float(slo.get(name, 0)) <= 0:
            raise ValueError(f"slo.{name} must be positive")
