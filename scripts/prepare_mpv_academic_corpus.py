"""Build the checksum-pinned MPV Level 2 corpus locally, without a shell."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from container_packing.data.mpv_corpus import (  # noqa: E402
    MpvGeneratorRun, create_mpv_capture_from_native_instances,
    import_mpv_bundle, normalize_mpv_capture, run_verified_mpv_generator,
)
from container_packing.data.mpv_workflow import (  # noqa: E402
    COMPILER_REQUIRED, build_mpv_capture_adapter, compiler_required_message,
    download_mpv_bundle, find_c_compiler, load_source_lock,
)


SCALES = (20, 50, 100)
CLASSES = tuple(range(1, 10))


def _import_downloaded_sources(lock: dict, source_dir: Path, destination_root: Path) -> Path:
    artifacts = []
    for value in lock["artifacts"]:
        artifacts.append({
            "role": value["role"], "path": str(source_dir / value["filename"]),
            "filename": value["filename"], "sha256": value["sha256"],
            "canonical_url": value["canonical_url"],
        })
    with tempfile.TemporaryDirectory(prefix="mpv-import-") as temporary:
        manifest = Path(temporary) / "bundle.yaml"
        manifest.write_text(yaml.safe_dump({
            "schema_version": "1.0", "bundle_id": lock["bundle_id"],
            "source_page": lock["source_page"], "checksum_source": lock["checksum_policy"],
            "license_note": lock["license_note"], "artifacts": artifacts,
        }, sort_keys=False, allow_unicode=True), encoding="utf-8")
        return import_mpv_bundle(manifest, destination_root=destination_root).import_manifest_path


def _execution_config(import_manifest: Path, build_provenance: Path, *, scale: int, instance_class: int) -> dict:
    execution_id = f"mpv-c{instance_class:02d}-n{scale:03d}-v1"
    return {
        "schema_version": "1.0", "execution_id": execution_id,
        "import_manifest": str(import_manifest), "build_provenance": str(build_provenance),
        "arguments": [str(scale), "100", str(instance_class), "0", "0", "1", "0"],
        "timeout_seconds": 300,
        "expected_output_files": [f"mpv_instance_{index:02d}.txt" for index in range(1, 11)],
    }


def _existing_verified_run(output_root: Path, execution: dict) -> MpvGeneratorRun | None:
    """Reuse only a complete, matching native run from a previous invocation."""
    destination = output_root / str(execution["execution_id"])
    manifest_path = destination / "execution_manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"MPV execution manifest cannot be reused: {manifest_path}: {exc}") from exc
    if (
        manifest.get("execution_id") != execution["execution_id"]
        or manifest.get("arguments") != execution["arguments"]
        or not isinstance(manifest.get("output_sha256"), dict)
    ):
        raise ValueError(f"MPV execution output conflicts with requested run: {destination}")
    for filename in execution["expected_output_files"]:
        path = destination / filename
        expected = manifest["output_sha256"].get(filename)
        if not path.is_file() or not expected:
            raise ValueError(f"MPV execution output is incomplete: {path}")
        if sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"MPV execution output checksum no longer matches: {path}")
    return MpvGeneratorRun(str(execution["execution_id"]), destination, manifest_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Tao corpus MPV Level 2 tu source chinh thuc da pin checksum.")
    parser.add_argument("--mode", choices=("smoke", "full"), default="smoke")
    parser.add_argument("--lock", type=Path, default=Path("config/level_02/mpv_source_lock.yaml"))
    parser.add_argument("--external-root", type=Path, default=Path("data/external/mpv_3dbpp"))
    parser.add_argument("--interim-root", type=Path, default=Path("data/interim/mpv_3dbpp"))
    args = parser.parse_args(argv)
    lock_path = args.lock if args.lock.is_absolute() else ROOT / args.lock
    external_root = args.external_root if args.external_root.is_absolute() else ROOT / args.external_root
    interim_root = args.interim_root if args.interim_root.is_absolute() else ROOT / args.interim_root
    lock = load_source_lock(lock_path)
    source_dir = download_mpv_bundle(lock_path, destination_root=external_root)
    import_manifest = _import_downloaded_sources(lock, source_dir, external_root)
    if find_c_compiler() is None:
        print(compiler_required_message(), file=sys.stderr)
        return 3
    build = build_mpv_capture_adapter(
        source_dir=source_dir, adapter_path=ROOT / "scripts/mpv_capture_adapter.c",
        build_root=interim_root / "builds",
    )
    classes = (1, 5, 9) if args.mode == "smoke" else CLASSES
    scales = (20,) if args.mode == "smoke" else SCALES
    catalog: list[dict] = []
    for instance_class in classes:
        for scale in scales:
            execution = _execution_config(import_manifest, build.provenance_path, scale=scale, instance_class=instance_class)
            execution_file = interim_root / "execution_configs" / f"{execution['execution_id']}.yaml"
            execution_file.parent.mkdir(parents=True, exist_ok=True)
            execution_file.write_text(yaml.safe_dump(execution, sort_keys=False), encoding="utf-8")
            output_root = interim_root / "raw_generator_runs"
            run = _existing_verified_run(output_root, execution)
            if run is None:
                run = run_verified_mpv_generator(execution_file, output_root=output_root)
            native = [run.output_dir / f"mpv_instance_{index:02d}.txt" for index in range(1, 11)]
            capture = interim_root / "captures" / f"{execution['execution_id']}.json"
            create_mpv_capture_from_native_instances(native, execution_manifest_path=run.execution_manifest_path,
                                                     import_manifest_path=import_manifest, output_path=capture)
            instance_id = f"MPV-{execution['execution_id']}-I01"
            normalized = normalize_mpv_capture(capture, import_manifest_path=import_manifest,
                                               output_dir=interim_root / "normalized" / execution["execution_id"],
                                               instance_id=instance_id, physical_container_count=scale)
            catalog.append({"case_id": execution["execution_id"], "class": instance_class, "item_count": scale,
                            "instance_id": instance_id, "normalized_manifest": str(normalized.manifest_path),
                            "capture": str(capture)})
    catalog_path = interim_root / f"corpus_catalog_{args.mode}_v1.json"
    catalog_path.write_text(json.dumps({"schema_version": "1.0", "mode": args.mode,
                                        "source_lock": str(lock_path), "build_provenance": str(build.provenance_path),
                                        "cases": catalog}, indent=2) + "\n", encoding="utf-8")
    print(f"MPV corpus catalog: {catalog_path}")
    print(f"Cases prepared    : {len(catalog)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
