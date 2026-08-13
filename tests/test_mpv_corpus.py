from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pandas as pd
import pytest
import yaml

from container_packing.data.mpv_corpus import (
    OFFICIAL_CODES_URL,
    create_mpv_capture_from_native_instances,
    import_mpv_bundle,
    normalize_mpv_capture,
    run_verified_mpv_generator,
)


def _write_bundle(
    tmp_path: Path, *, bad_solver_checksum: bool = False,
    include_executable: bool = False,
) -> Path:
    artifacts = []
    roles = [
        ("generator_source", "test3dbpp.c"),
        ("solver_source", "3dbpp.c"),
        ("compilation_readme", "readme.txt"),
    ]
    if include_executable:
        roles.append(("generator_executable", "test3dbpp.exe"))
    for role, filename in roles:
        payload = f"official fixture for {role}\n".encode()
        path = tmp_path / filename
        path.write_bytes(payload)
        digest = sha256(payload).hexdigest()
        if bad_solver_checksum and role == "solver_source":
            digest = "0" * 64
        artifacts.append({
            "role": role,
            "path": filename,
            "filename": filename,
            "sha256": digest,
            "canonical_url": f"https://hjemmesider.diku.dk/~pisinger/new3dbpp/{filename}",
        })
    manifest = tmp_path / "bundle.yaml"
    manifest.write_text(yaml.safe_dump({
        "schema_version": "1.0",
        "bundle_id": "mpv-test-bundle-v1",
        "source_page": OFFICIAL_CODES_URL,
        "checksum_source": "independent release ledger",
        "license_note": "academic use fixture",
        "artifacts": artifacts,
    }, sort_keys=False), encoding="utf-8")
    return manifest


def test_import_mpv_bundle_verifies_complete_bundle_before_publish(tmp_path) -> None:
    manifest = _write_bundle(tmp_path)
    destination = tmp_path / "external"
    first = import_mpv_bundle(manifest, destination_root=destination)
    second = import_mpv_bundle(manifest, destination_root=destination)
    assert first.bundle_checksum == second.bundle_checksum
    assert {value.role for value in first.artifacts} == {
        "generator_source", "solver_source", "compilation_readme",
    }
    evidence = json.loads(first.import_manifest_path.read_text(encoding="utf-8"))
    assert evidence["source_page"] == OFFICIAL_CODES_URL
    assert evidence["bundle_checksum"] == first.bundle_checksum


def test_import_mpv_bundle_checksum_failure_publishes_nothing(tmp_path) -> None:
    manifest = _write_bundle(tmp_path, bad_solver_checksum=True)
    destination = tmp_path / "external"
    with pytest.raises(ValueError, match="solver_source"):
        import_mpv_bundle(manifest, destination_root=destination)
    assert not (destination / "imported").exists()


def test_import_mpv_bundle_requires_companion_artifacts(tmp_path) -> None:
    manifest = _write_bundle(tmp_path)
    payload = yaml.safe_load(manifest.read_text(encoding="utf-8"))
    payload["artifacts"] = payload["artifacts"][:1]
    manifest.write_text(yaml.safe_dump(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="required roles"):
        import_mpv_bundle(manifest, destination_root=tmp_path / "external")


def test_normalize_mpv_capture_is_deterministic_and_fixed_orientation(tmp_path) -> None:
    imported = import_mpv_bundle(
        _write_bundle(tmp_path), destination_root=tmp_path / "external",
    )
    capture = tmp_path / "capture.json"
    capture.write_text(json.dumps({
        "schema_version": "1.0",
        "source_bundle_checksum": imported.bundle_checksum,
        "generator_parameters": {"class": 1, "seed": 42},
        "instances": [{
            "instance_id": "MPV-C01-N003-S42",
            "bin": {"length": 1000, "width": 1000, "height": 1000},
            "items": [
                {"item_id": "I1", "length": 500, "width": 500, "height": 500},
                {"item_id": "I2", "length": 400, "width": 300, "height": 200},
                {"item_id": "I3", "length": 250, "width": 250, "height": 250},
            ],
        }],
    }), encoding="utf-8")
    output = tmp_path / "interim" / "mpv"
    first = normalize_mpv_capture(
        capture, import_manifest_path=imported.import_manifest_path,
        output_dir=output, instance_id="MPV-C01-N003-S42",
    )
    second = normalize_mpv_capture(
        capture, import_manifest_path=imported.import_manifest_path,
        output_dir=output, instance_id="MPV-C01-N003-S42",
    )
    assert first == second
    items = pd.read_csv(output / "solver_items.csv")
    containers = pd.read_csv(output / "solver_containers.csv")
    manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    assert len(items) == 3
    assert len(containers) == 3
    assert list(items.loc[0, ["length", "width", "height"]]) == [500.0, 500.0, 500.0]
    assert manifest["semantics"] == "fixed_orientation_with_level_02_exact_support"
    assert manifest["best_known_comparison_allowed"] is False
    assert not Path(manifest["source_capture_filename"]).is_absolute()


def test_normalize_mpv_capture_rejects_unverified_bundle_and_oversized_item(tmp_path) -> None:
    imported = import_mpv_bundle(
        _write_bundle(tmp_path), destination_root=tmp_path / "external",
    )
    capture = tmp_path / "capture.json"
    capture.write_text(json.dumps({
        "schema_version": "1.0",
        "source_bundle_checksum": "f" * 64,
        "generator_parameters": {"seed": 42},
        "instances": [{
            "instance_id": "bad", "bin": {"length": 10, "width": 10, "height": 10},
            "items": [{"item_id": "I1", "length": 11, "width": 1, "height": 1}],
        }],
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="source_bundle_checksum"):
        normalize_mpv_capture(
            capture, import_manifest_path=imported.import_manifest_path,
            output_dir=tmp_path / "out", instance_id="bad",
        )


def test_verified_generator_runs_without_shell_and_publishes_complete_output(tmp_path) -> None:
    imported = import_mpv_bundle(
        _write_bundle(tmp_path, include_executable=True),
        destination_root=tmp_path / "external",
    )
    config = tmp_path / "execution.yaml"
    config.write_text(yaml.safe_dump({
        "schema_version": "1.0",
        "execution_id": "class01-seed42",
        "import_manifest": str(imported.import_manifest_path),
        "executable_role": "generator_executable",
        "arguments": ["--seed", "42"],
        "timeout_seconds": 5,
        "expected_output_files": ["raw.txt"],
    }), encoding="utf-8")
    observed = {}

    def fake_runner(command, **kwargs):
        observed.update({"command": command, **kwargs})
        (Path(kwargs["cwd"]) / "raw.txt").write_text("official raw output", encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout=b"stdout", stderr=b"")

    result = run_verified_mpv_generator(
        config, output_root=tmp_path / "raw-runs", runner=fake_runner,
    )
    evidence = json.loads(result.execution_manifest_path.read_text(encoding="utf-8"))
    assert observed["shell"] is False
    assert observed["command"][-2:] == ["--seed", "42"]
    assert (result.output_dir / "raw.txt").read_text(encoding="utf-8") == "official raw output"
    assert evidence["source_bundle_checksum"] == imported.bundle_checksum
    assert evidence["return_code"] == 0


def test_verified_generator_timeout_does_not_publish_partial_output(tmp_path) -> None:
    imported = import_mpv_bundle(
        _write_bundle(tmp_path, include_executable=True),
        destination_root=tmp_path / "external",
    )
    config = tmp_path / "execution.yaml"
    config.write_text(yaml.safe_dump({
        "schema_version": "1.0", "execution_id": "timeout-case",
        "import_manifest": str(imported.import_manifest_path),
        "expected_output_files": ["raw.txt"], "timeout_seconds": 1,
    }), encoding="utf-8")

    def timeout_runner(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 1)

    with pytest.raises(TimeoutError, match="timeout_seconds"):
        run_verified_mpv_generator(
            config, output_root=tmp_path / "raw-runs", runner=timeout_runner,
        )
    assert not (tmp_path / "raw-runs" / "timeout-case").exists()


def test_native_mpv_instance_capture_is_checksum_pinned_and_deterministic(tmp_path) -> None:
    imported = import_mpv_bundle(
        _write_bundle(tmp_path), destination_root=tmp_path / "external",
    )
    native = tmp_path / "mpv_instance_01.txt"
    native.write_text("3 100 80 60\n50 40 30\n20 10 5\n1 2 3\n", encoding="ascii")
    execution = tmp_path / "execution_manifest.json"
    execution.write_text(json.dumps({
        "schema_version": "1.0",
        "execution_id": "class01-n003",
        "source_bundle_checksum": imported.bundle_checksum,
        "executable_sha256": "e" * 64,
        "arguments": ["3", "100", "1", "0", "0", "1", "0"],
        "output_sha256": {native.name: sha256(native.read_bytes()).hexdigest()},
    }), encoding="utf-8")
    output = tmp_path / "derived" / "capture.json"
    first = create_mpv_capture_from_native_instances(
        [native], execution_manifest_path=execution,
        import_manifest_path=imported.import_manifest_path, output_path=output,
    )
    second = create_mpv_capture_from_native_instances(
        [native], execution_manifest_path=execution,
        import_manifest_path=imported.import_manifest_path, output_path=output,
    )
    assert first == second
    capture = json.loads(output.read_text(encoding="utf-8"))
    assert capture["generator_parameters"]["native_format"] == "mpv_readme_3dbpp_v1"
    assert capture["instances"][0]["bin"] == {
        "length": 100, "width": 80, "height": 60,
    }
    assert len(capture["instances"][0]["items"]) == 3


def test_native_mpv_instance_capture_rejects_tampering_and_bad_shape(tmp_path) -> None:
    imported = import_mpv_bundle(
        _write_bundle(tmp_path), destination_root=tmp_path / "external",
    )
    native = tmp_path / "mpv_instance_01.txt"
    native.write_text("2 10 10 10\n1 2 3\n", encoding="ascii")
    execution = tmp_path / "execution_manifest.json"
    execution.write_text(json.dumps({
        "source_bundle_checksum": imported.bundle_checksum,
        "output_sha256": {native.name: sha256(native.read_bytes()).hexdigest()},
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="declares 2 items"):
        create_mpv_capture_from_native_instances(
            [native], execution_manifest_path=execution,
            import_manifest_path=imported.import_manifest_path,
            output_path=tmp_path / "capture.json",
        )
    native.write_text("1 10 10 10\n1 2 3\n", encoding="ascii")
    with pytest.raises(ValueError, match="SHA-256"):
        create_mpv_capture_from_native_instances(
            [native], execution_manifest_path=execution,
            import_manifest_path=imported.import_manifest_path,
            output_path=tmp_path / "capture.json",
        )
