from __future__ import annotations

import csv
import json
from pathlib import Path

import pandas as pd
import pytest

from container_packing.large_scale_web_gate import (
    EXPECTED_SUITE_ID,
    REQUIRED_ITEM_COUNTS,
    qualify_large_scale_web_profile,
)
from container_packing.provenance import sha256_file
from container_packing.solver_research_subset import (
    SolverResearchSubsetRequest,
    materialize_solver_research_subset,
)


def _source_manifest(tmp_path: Path, *, oversized: bool = False) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    items = source / "solver_items.csv"
    containers = source / "solver_containers.csv"
    with items.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "id_item", "length", "width", "height", "weight", "synthetic_profile_id",
        ])
        writer.writeheader()
        writer.writerow({
            "id_item": "I1", "length": 100 if oversized else 1, "width": 1,
            "height": 1, "weight": 1, "synthetic_profile_id": "source",
        })
        writer.writerow({
            "id_item": "I2", "length": 1, "width": 1, "height": 1,
            "weight": 1, "synthetic_profile_id": "source",
        })
    with containers.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[
            "container_id", "container_type_id", "length_mm", "width_mm", "height_mm",
            "max_weight_kg", "availability", "synthetic_profile_id",
        ])
        writer.writeheader()
        writer.writerow({
            "container_id": "C1", "container_type_id": "T1", "length_mm": 10,
            "width_mm": 10, "height_mm": 10, "max_weight_kg": 10,
            "availability": 1, "synthetic_profile_id": "source",
        })
        writer.writerow({
            "container_id": "C2", "container_type_id": "T1", "length_mm": 10,
            "width_mm": 10, "height_mm": 10, "max_weight_kg": 10,
            "availability": 1, "synthetic_profile_id": "source",
        })
    manifest = source / "generation_manifest.json"
    manifest.write_text(json.dumps({
        "schema_version": "2.0",
        "generator_id": "empirical_template_physical_instances_v1",
        "profile_id": "pipeline_source",
        "usage_class": "data_pipeline_only",
        "item_template_count": 2,
        "files": {"solver_items": items.name, "solver_containers": containers.name},
        "file_sha256": {
            "solver_items": sha256_file(items),
            "solver_containers": sha256_file(containers),
        },
    }, indent=2), encoding="utf-8")
    return manifest


def test_materialized_solver_research_subset_is_deterministic_and_qualified(tmp_path: Path) -> None:
    request = SolverResearchSubsetRequest(
        source_manifest=_source_manifest(tmp_path),
        output_dir=tmp_path / "derived",
        profile_id="derived_v1",
        item_count=2,
        minimum_volume_margin_ratio=1.4,
        minimum_payload_margin_ratio=1.4,
    )
    first = materialize_solver_research_subset(request)
    second = materialize_solver_research_subset(request)
    assert first == second
    manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    assert manifest["generator_id"] == "solver_research_subset_v1"
    assert manifest["usage_class"] == "solver_research"
    assert manifest["capacity_qualification"] == "solver_qualified"
    assert manifest["solver_acceptance_allowed"] is True
    assert manifest["source"]["profile_id"] == "pipeline_source"
    rows = list(csv.DictReader((first.output_dir / "solver_items.csv").open(encoding="utf-8")))
    assert [row["id_item"] for row in rows] == ["I1", "I2"]
    assert {row["synthetic_profile_id"] for row in rows} == {"derived_v1"}


def test_materializer_rejects_incompatible_item_without_publishing(tmp_path: Path) -> None:
    output = tmp_path / "derived"
    with pytest.raises(ValueError, match="incompatible"):
        materialize_solver_research_subset(SolverResearchSubsetRequest(
            source_manifest=_source_manifest(tmp_path, oversized=True),
            output_dir=output,
            item_count=2,
        ))
    assert not output.exists()


def test_large_web_gate_requires_all_scales_and_deterministic_valid_rows(tmp_path: Path) -> None:
    derived = materialize_solver_research_subset(SolverResearchSubsetRequest(
        source_manifest=_source_manifest(tmp_path),
        output_dir=tmp_path / "derived",
        profile_id="level_02_solver_research_i20000_f5000_v1",
        item_count=2,
    ))
    run_dir = tmp_path / "run"
    benchmark_dir = run_dir / "benchmark"
    benchmark_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(json.dumps({
        "run_id": "gate-run", "suite_id": EXPECTED_SUITE_ID,
    }), encoding="utf-8")
    rows = []
    for count in sorted(REQUIRED_ITEM_COUNTS):
        for repeat in (1, 2):
            rows.append({
                "item_count": count, "algorithm": "extreme_point_best_fit",
                "random_seed": 42, "repeat": repeat, "status": "FEASIBLE",
                "success": True, "validation_valid": True, "objective_value": count,
                "official_objective": "{'used_container_count': 1, 'total_container_cost': 1}",
                "placement_signature": f"signature-{count}", "peak_rss_bytes": 1024,
            })
    pd.DataFrame(rows).to_csv(benchmark_dir / "results.csv", index=False)
    gate = qualify_large_scale_web_profile(
        run_dir, derived.manifest_path, derived.output_dir / "web_qualification.json",
    )
    assert gate.qualified
    payload = json.loads(gate.gate_path.read_text(encoding="utf-8"))
    assert payload["dataset_profile_id"] == derived.profile_id
    assert payload["item_counts"] == sorted(REQUIRED_ITEM_COUNTS)
