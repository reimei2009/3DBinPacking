from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from container_packing.dataset_inspection import (
    DatasetInspectionRequest,
    InspectionMode,
    inspect_generated_dataset,
)
from container_packing.provenance import sha256_file
from container_packing.synthetic_instances import (
    generate_large_synthetic_instances,
    load_large_synthetic_profile,
)


def _generated_manifest(root: Path, tmp_path: Path, *, item_count: int = 12) -> Path:
    base = load_large_synthetic_profile("config/synthetic/scale_1k_100.yaml", root=root)
    profile = replace(
        base,
        item_count=item_count,
        delivery_stop_count=3,
        container_quantities={"C1": 0, "C2": 0, "C3": 0, "C4": 0, "C5": 2},
        output_dir=tmp_path / "generated",
    )
    result = generate_large_synthetic_instances(profile)
    return Path(result["manifest_path"])


@pytest.mark.parametrize("mode", list(InspectionMode))
def test_generated_dataset_inspection_modes_are_valid_and_isolated(
    root: Path, tmp_path: Path, mode: InspectionMode,
) -> None:
    manifest = _generated_manifest(root, tmp_path)
    result = inspect_generated_dataset(DatasetInspectionRequest(
        manifest_path=manifest,
        mode=mode,
        output_root=tmp_path / "outputs",
        project_root=root,
    ))

    assert result.valid
    assert result.run_dir.parent.parent.name == "level_08"
    assert result.provenance.status == "VALID"
    assert (result.stream is not None) == (mode in {InspectionMode.STREAM, InspectionMode.BOTH})
    assert (result.materialize is not None) == (mode in {InspectionMode.MATERIALIZE, InspectionMode.BOTH})
    assert (result.run_dir / "resolved_config.yaml").is_file()
    assert (result.run_dir / "input_snapshot/generation_manifest.json").is_file()
    report = json.loads((result.run_dir / "reports/dataset_inspection.json").read_text(encoding="utf-8"))
    run_manifest = json.loads((result.run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert report["solver_invoked"] is False
    assert report["objective_value"] is None
    assert run_manifest["run_type"] == "dataset_inspection"
    assert run_manifest["solver_invoked"] is False
    assert run_manifest["objective_value"] is None
    assert "ITEM-" not in json.dumps(report)


def test_stream_inspection_detects_cross_file_identity_mismatch_after_checksum_refresh(
    root: Path, tmp_path: Path,
) -> None:
    manifest_path = _generated_manifest(root, tmp_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    delivery_path = manifest_path.parent / payload["files"]["delivery"]
    text = delivery_path.read_text(encoding="utf-8-sig")
    delivery_path.write_text(text.replace("ITEM-000000001", "ITEM-999999999", 1), encoding="utf-8-sig")
    payload["file_sha256"]["delivery"] = sha256_file(delivery_path)
    manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    result = inspect_generated_dataset(DatasetInspectionRequest(
        manifest_path=manifest_path,
        mode=InspectionMode.BOTH,
        output_root=tmp_path / "outputs",
        project_root=root,
    ))

    assert result.status == "INVALID"
    assert result.provenance.status == "VALID"
    assert result.stream is not None and result.stream.status == "INVALID"
    assert result.materialize is None
    assert any("identity mismatch" in issue.message for issue in result.issues)


def test_inspection_rejects_checksum_tampering_before_read_modes(root: Path, tmp_path: Path) -> None:
    manifest_path = _generated_manifest(root, tmp_path)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    items_path = manifest_path.parent / payload["files"]["solver_items"]
    with items_path.open("a", encoding="utf-8") as handle:
        handle.write("tampered\n")

    result = inspect_generated_dataset(DatasetInspectionRequest(
        manifest_path=manifest_path,
        mode=InspectionMode.BOTH,
        output_root=tmp_path / "outputs",
        project_root=root,
    ))

    assert result.status == "INVALID"
    assert result.provenance.status == "INVALID"
    assert result.stream is None
    assert result.materialize is None
    assert any("checksum mismatch" in issue.message for issue in result.issues)


def test_inspection_refuses_non_level_output_namespace(root: Path, tmp_path: Path) -> None:
    manifest_path = _generated_manifest(root, tmp_path)
    with pytest.raises(ValueError, match="level_XX"):
        inspect_generated_dataset(DatasetInspectionRequest(
            manifest_path=manifest_path,
            level_id="shared",
            output_root=tmp_path / "outputs",
            project_root=root,
        ))
