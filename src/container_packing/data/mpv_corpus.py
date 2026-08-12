"""Import and normalize pinned Martello--Pisinger--Vigo corpus artifacts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import os
import shutil
import subprocess
from tempfile import TemporaryDirectory
from typing import Any
from urllib.parse import urlparse

import pandas as pd
import yaml

from .external_sources import import_pinned_local_source


OFFICIAL_CODES_URL = "https://hjemmesider.diku.dk/~pisinger/codes.html"
REQUIRED_BUNDLE_ROLES = frozenset({
    "generator_source", "solver_source", "compilation_readme",
})
CAPTURE_SCHEMA_VERSION = "1.0"
BUNDLE_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class ImportedMpvArtifact:
    role: str
    filename: str
    sha256: str
    canonical_url: str


@dataclass(frozen=True)
class ImportedMpvBundle:
    bundle_id: str
    bundle_checksum: str
    import_manifest_path: Path
    artifacts: tuple[ImportedMpvArtifact, ...]


@dataclass(frozen=True)
class NormalizedMpvCorpus:
    corpus_id: str
    item_count: int
    container_count: int
    output_dir: Path
    manifest_path: Path


@dataclass(frozen=True)
class MpvGeneratorRun:
    execution_id: str
    output_dir: Path
    execution_manifest_path: Path


def create_mpv_capture_from_native_instances(
    instance_paths: list[str | Path],
    *,
    execution_manifest_path: str | Path,
    import_manifest_path: str | Path,
    output_path: str | Path,
) -> Path:
    """Convert checksum-pinned native MPV instances to the capture contract.

    The native format is defined by the official ``readme.3dbpp``. Files are
    accepted only when their hashes occur in the isolated execution manifest.
    """
    execution_manifest_path = Path(execution_manifest_path).resolve()
    import_manifest_path = Path(import_manifest_path).resolve()
    execution = _read_mapping(
        execution_manifest_path, description="MPV generator execution manifest",
    )
    imported = _read_mapping(import_manifest_path, description="MPV import manifest")
    if str(execution.get("source_bundle_checksum", "")) != str(
        imported.get("bundle_checksum", "")
    ):
        raise ValueError("MPV execution manifest does not match the imported source bundle")
    declared_hashes = execution.get("output_sha256")
    if not isinstance(declared_hashes, dict):
        raise ValueError("MPV execution manifest requires output_sha256")
    if not instance_paths:
        raise ValueError("At least one native MPV instance is required")

    instances: list[dict[str, Any]] = []
    source_files: list[dict[str, str]] = []
    for index, value in enumerate(instance_paths, start=1):
        path = Path(value).resolve()
        if not path.is_file():
            raise ValueError(f"Native MPV instance does not exist: {path}")
        expected = str(declared_hashes.get(path.name, "")).lower()
        actual = _sha256_file(path)
        if not expected or expected != actual:
            raise ValueError(
                f"Native MPV instance {path.name} is absent from execution evidence "
                "or no longer matches its SHA-256"
            )
        instance = _parse_native_mpv_instance(path)
        instance["instance_id"] = (
            f"MPV-{execution.get('execution_id', 'RUN')}-I{index:02d}"
        )
        instances.append(instance)
        source_files.append({"filename": path.name, "sha256": actual})

    capture = {
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "source_bundle_checksum": imported["bundle_checksum"],
        "generator_parameters": {
            "execution_id": execution.get("execution_id"),
            "arguments": execution.get("arguments", []),
            "executable_sha256": execution.get("executable_sha256"),
            "native_format": "mpv_readme_3dbpp_v1",
            "source_files": source_files,
        },
        "instances": instances,
    }
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(capture, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    ).encode("utf-8")
    _write_bytes_if_new_or_identical(output_path, encoded)
    return output_path


def _parse_native_mpv_instance(path: Path) -> dict[str, Any]:
    try:
        tokens = [int(value) for value in path.read_text(encoding="ascii").split()]
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"Cannot parse native MPV instance {path}: {exc}") from exc
    if len(tokens) < 4:
        raise ValueError(f"Native MPV instance {path} is missing the n W H D header")
    item_count, length, width, height = tokens[:4]
    if item_count <= 0 or min(length, width, height) <= 0:
        raise ValueError(f"Native MPV instance {path} has non-positive header values")
    expected_count = 4 + 3 * item_count
    if len(tokens) != expected_count:
        raise ValueError(
            f"Native MPV instance {path} declares {item_count} items but contains "
            f"{len(tokens) - 4} dimension values; expected {3 * item_count}"
        )
    items: list[dict[str, Any]] = []
    for index in range(item_count):
        offset = 4 + 3 * index
        item_length, item_width, item_height = tokens[offset:offset + 3]
        if min(item_length, item_width, item_height) <= 0:
            raise ValueError(f"Native MPV instance {path} item {index + 1} is non-positive")
        items.append({
            "item_id": f"I{index + 1:04d}",
            "length": item_length,
            "width": item_width,
            "height": item_height,
        })
    return {
        "bin": {"length": length, "width": width, "height": height},
        "items": items,
    }


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _read_mapping(path: Path, *, description: str) -> dict[str, Any]:
    try:
        if path.suffix.lower() == ".json":
            value = json.loads(path.read_text(encoding="utf-8"))
        else:
            value = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"Cannot read {description} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{description} {path} must contain a mapping")
    return value


def import_mpv_bundle(
    manifest_path: str | Path, *, destination_root: str | Path,
) -> ImportedMpvBundle:
    """Import a complete local source bundle after verifying every checksum."""
    manifest_path = Path(manifest_path).resolve()
    payload = _read_mapping(manifest_path, description="MPV bundle manifest")
    if str(payload.get("schema_version")) != BUNDLE_SCHEMA_VERSION:
        raise ValueError("MPV bundle manifest schema_version must be '1.0'")
    bundle_id = str(payload.get("bundle_id", "")).strip()
    if not bundle_id or any(value not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for value in bundle_id):
        raise ValueError("MPV bundle_id must use lowercase letters, digits, '_' or '-'")
    if str(payload.get("source_page", "")) != OFFICIAL_CODES_URL:
        raise ValueError(f"MPV source_page must be the canonical URL {OFFICIAL_CODES_URL}")
    checksum_source = str(payload.get("checksum_source", "")).strip()
    license_note = str(payload.get("license_note", "")).strip()
    if not checksum_source or not license_note:
        raise ValueError("MPV bundle requires checksum_source and license_note")
    raw_artifacts = payload.get("artifacts")
    if not isinstance(raw_artifacts, list) or not raw_artifacts:
        raise ValueError("MPV bundle artifacts must be a non-empty list")
    roles = [str(value.get("role", "")) for value in raw_artifacts if isinstance(value, dict)]
    missing = sorted(REQUIRED_BUNDLE_ROLES - set(roles))
    if missing:
        raise ValueError("MPV bundle is missing required roles: " + ", ".join(missing))
    if len(roles) != len(set(roles)):
        raise ValueError("MPV bundle artifact roles must be unique")

    destination = Path(destination_root).resolve() / "imported" / bundle_id
    verified: list[tuple[Path, ImportedMpvArtifact]] = []
    for index, raw in enumerate(raw_artifacts, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"MPV artifact {index} must be a mapping")
        role = str(raw.get("role", "")).strip()
        source_value = str(raw.get("path", "")).strip()
        filename = str(raw.get("filename", Path(source_value).name)).strip()
        expected = str(raw.get("sha256", "")).strip().lower()
        canonical_url = str(raw.get("canonical_url", "")).strip()
        if not role or not source_value or not filename or Path(filename).name != filename:
            raise ValueError(f"MPV artifact {index} has invalid role, path, or filename")
        parsed_url = urlparse(canonical_url)
        if (
            parsed_url.scheme != "https"
            or parsed_url.hostname != "hjemmesider.diku.dk"
            or not parsed_url.path.startswith("/~pisinger/")
        ):
            raise ValueError(
                f"MPV artifact {role} canonical_url must use the official HTTPS Pisinger host"
            )
        source = Path(source_value)
        source = source.resolve() if source.is_absolute() else (manifest_path.parent / source).resolve()
        if len(expected) != 64 or any(value not in "0123456789abcdef" for value in expected):
            raise ValueError(f"MPV artifact {role} sha256 must contain 64 hexadecimal characters")
        if not source.is_file():
            raise ValueError(f"MPV artifact {role} does not exist: {source}")
        actual = _sha256_file(source)
        if actual != expected:
            raise ValueError(
                f"SHA-256 mismatch for MPV artifact {role}: expected {expected}, got {actual}"
            )
        verified.append((source, ImportedMpvArtifact(role, filename, expected, canonical_url)))

    # No destination is touched until the complete bundle has been verified.
    imported: list[ImportedMpvArtifact] = []
    for source, artifact in verified:
        import_pinned_local_source(
            source=source,
            expected_sha256=artifact.sha256,
            destination=destination / artifact.filename,
        )
        imported.append(artifact)

    bundle_digest = sha256()
    for artifact in sorted(imported, key=lambda value: value.role):
        bundle_digest.update(artifact.role.encode("utf-8"))
        bundle_digest.update(b"\0")
        bundle_digest.update(artifact.sha256.encode("ascii"))
        bundle_digest.update(b"\0")
    bundle_checksum = bundle_digest.hexdigest()
    evidence = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "bundle_id": bundle_id,
        "bundle_checksum": bundle_checksum,
        "source_page": OFFICIAL_CODES_URL,
        "checksum_source": checksum_source,
        "license_note": license_note,
        "imported_at_utc": datetime.now(timezone.utc).isoformat(),
        "artifacts": [asdict(value) for value in imported],
    }
    evidence_path = destination / "import_manifest.json"
    encoded = json.dumps(evidence, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if evidence_path.exists():
        previous = _read_mapping(evidence_path, description="MPV import manifest")
        previous.pop("imported_at_utc", None)
        comparable = dict(evidence)
        comparable.pop("imported_at_utc", None)
        if previous != comparable:
            raise FileExistsError(f"Refusing to replace different MPV import evidence: {evidence_path}")
    else:
        evidence_path.write_text(encoded, encoding="utf-8")
    return ImportedMpvBundle(bundle_id, bundle_checksum, evidence_path, tuple(imported))


def normalize_mpv_capture(
    capture_path: str | Path,
    *, import_manifest_path: str | Path,
    output_dir: str | Path,
    instance_id: str,
    physical_container_count: int | None = None,
    container_cost: float = 1.0,
) -> NormalizedMpvCorpus:
    """Normalize a versioned capture emitted from a verified official bundle.

    The capture is deliberately explicit JSON.  We do not guess the native C
    output format before the pinned source bundle has been inspected.
    """
    capture_path = Path(capture_path).resolve()
    import_manifest_path = Path(import_manifest_path).resolve()
    capture = _read_mapping(capture_path, description="MPV generated capture")
    imported = _read_mapping(import_manifest_path, description="MPV import manifest")
    if str(capture.get("schema_version")) != CAPTURE_SCHEMA_VERSION:
        raise ValueError("MPV capture schema_version must be '1.0'")
    if str(capture.get("source_bundle_checksum", "")) != str(imported.get("bundle_checksum", "")):
        raise ValueError("MPV capture source_bundle_checksum does not match imported source bundle")
    generator_parameters = capture.get("generator_parameters")
    if not isinstance(generator_parameters, dict) or not generator_parameters:
        raise ValueError("MPV capture requires non-empty generator_parameters")
    instances = capture.get("instances")
    if not isinstance(instances, list) or not instances:
        raise ValueError("MPV capture must contain one or more instances")
    selected = next((value for value in instances if isinstance(value, dict) and str(value.get("instance_id")) == instance_id), None)
    if selected is None:
        raise ValueError(f"MPV capture does not contain instance_id {instance_id!r}")
    bin_data = selected.get("bin")
    items = selected.get("items")
    if not isinstance(bin_data, dict) or not isinstance(items, list) or not items:
        raise ValueError(f"MPV instance {instance_id} requires bin and non-empty items")
    bin_length = _positive_number(bin_data.get("length"), "bin.length")
    bin_width = _positive_number(bin_data.get("width"), "bin.width")
    bin_height = _positive_number(bin_data.get("height"), "bin.height")
    item_rows: list[dict[str, Any]] = []
    seen_items: set[str] = set()
    total_volume = 0.0
    for index, raw in enumerate(items, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"MPV instance {instance_id} item {index} must be a mapping")
        item_id = str(raw.get("item_id", f"{instance_id}-I{index:04d}")).strip()
        if not item_id or item_id in seen_items:
            raise ValueError(f"MPV instance {instance_id} has empty or duplicate item_id {item_id!r}")
        seen_items.add(item_id)
        length = _positive_number(raw.get("length"), f"items[{index}].length")
        width = _positive_number(raw.get("width"), f"items[{index}].width")
        height = _positive_number(raw.get("height"), f"items[{index}].height")
        if length > bin_length or width > bin_width or height > bin_height:
            raise ValueError(f"MPV item {item_id} does not fit the bin in fixed orientation")
        total_volume += length * width * height
        item_rows.append({
            "id_item": item_id, "length": length, "width": width, "height": height,
            "weight": _positive_number(raw.get("weight", 1.0), f"items[{index}].weight"),
            "mpv_instance_id": instance_id, "mpv_item_index": index,
            "source_bundle_checksum": imported["bundle_checksum"],
        })
    minimum_count = max(1, int(-(-total_volume // (bin_length * bin_width * bin_height))))
    count = int(physical_container_count or len(item_rows))
    if count < minimum_count:
        raise ValueError(
            f"physical_container_count={count} is below aggregate volume lower bound {minimum_count}"
        )
    cost = _positive_number(container_cost, "container_cost")
    # MPV does not model payload.  A conservative synthetic payload avoids
    # activating a non-source constraint while still satisfying our schema.
    total_weight = sum(float(row["weight"]) for row in item_rows)
    payload = max(total_weight, 1.0)
    container_rows = [{
        "container_id": f"{instance_id}-C{index:04d}",
        "length_mm": bin_length, "width_mm": bin_width, "height_mm": bin_height,
        "max_weight_kg": payload, "availability": 1, "cost": cost,
        "volume_m3": bin_length * bin_width * bin_height / 1_000_000_000.0,
        "data_status": "mpv_fixed_orientation_physical_instance_v1",
    } for index in range(1, count + 1)]

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    items_path = output_dir / "solver_items.csv"
    containers_path = output_dir / "solver_containers.csv"
    manifest_path = output_dir / "generation_manifest.json"
    _write_bytes_if_new_or_identical(
        items_path, pd.DataFrame(item_rows).to_csv(index=False, lineterminator="\n").encode("utf-8"),
    )
    _write_bytes_if_new_or_identical(
        containers_path,
        pd.DataFrame(container_rows).to_csv(index=False, lineterminator="\n").encode("utf-8"),
    )
    corpus_id = f"mpv_fixed_orientation_{instance_id}_v1"
    manifest = {
        "schema_version": "1.0",
        "generator_id": "official_mpv_capture_normalizer_v1",
        "corpus_id": corpus_id,
        "instance_id": instance_id,
        "semantics": "fixed_orientation_with_level_02_exact_support",
        "best_known_comparison_allowed": False,
        "source_page": OFFICIAL_CODES_URL,
        "source_bundle_checksum": imported["bundle_checksum"],
        "source_import_manifest_filename": import_manifest_path.name,
        "source_import_manifest_sha256": _sha256_file(import_manifest_path),
        "source_capture_filename": capture_path.name,
        "source_capture_sha256": _sha256_file(capture_path),
        "generator_parameters": generator_parameters,
        "item_count": len(item_rows),
        "container_count": count,
        "container_cost": cost,
        "files": {"solver_items": items_path.name, "solver_containers": containers_path.name},
        "file_sha256": {
            "solver_items": _sha256_file(items_path),
            "solver_containers": _sha256_file(containers_path),
        },
    }
    _write_bytes_if_new_or_identical(
        manifest_path,
        (json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"),
    )
    return NormalizedMpvCorpus(corpus_id, len(item_rows), count, output_dir, manifest_path)


def run_verified_mpv_generator(
    execution_config_path: str | Path,
    *, output_root: str | Path,
    runner: Any = subprocess.run,
) -> MpvGeneratorRun:
    """Run a pinned generator executable without a shell in a temporary cwd."""
    config_path = Path(execution_config_path).resolve()
    config = _read_mapping(config_path, description="MPV generator execution config")
    if str(config.get("schema_version")) != "1.0":
        raise ValueError("MPV generator execution config schema_version must be '1.0'")
    execution_id = str(config.get("execution_id", "")).strip()
    if not execution_id or any(value not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for value in execution_id):
        raise ValueError("MPV execution_id must use lowercase letters, digits, '_' or '-'")
    import_value = str(config.get("import_manifest", "")).strip()
    if not import_value:
        raise ValueError("MPV execution config requires import_manifest")
    import_path = Path(import_value)
    import_path = import_path.resolve() if import_path.is_absolute() else (config_path.parent / import_path).resolve()
    imported = _read_mapping(import_path, description="MPV import manifest")
    executable_role = str(config.get("executable_role", "generator_executable"))
    build_provenance_value = str(config.get("build_provenance", "")).strip()
    if build_provenance_value:
        build_path = Path(build_provenance_value)
        build_path = build_path.resolve() if build_path.is_absolute() else (config_path.parent / build_path).resolve()
        build = _read_mapping(build_path, description="MPV local build provenance")
        source_hashes = build.get("source_file_sha256")
        if not isinstance(source_hashes, dict):
            raise ValueError("MPV local build provenance requires source_file_sha256")
        imported_hashes = {str(value.get("filename")): str(value.get("sha256", "")) for value in imported.get("artifacts", []) if isinstance(value, dict)}
        if any(imported_hashes.get(name) != value for name, value in source_hashes.items()):
            raise ValueError("MPV local build provenance does not match the imported source bundle")
        executable = build_path.parent / str(build.get("executable_filename", ""))
        if not executable.is_file() or _sha256_file(executable) != str(build.get("executable_sha256", "")):
            raise ValueError("MPV locally built capture executable is missing or no longer matches its checksum")
    else:
        artifact = next((
            value for value in imported.get("artifacts", [])
            if isinstance(value, dict) and str(value.get("role")) == executable_role
        ), None)
        if artifact is None:
            raise ValueError(
                f"Imported MPV bundle does not declare {executable_role!r}; compile the verified "
                "source in a controlled environment and import the executable with its checksum"
            )
        executable = import_path.parent / str(artifact.get("filename", ""))
        if not executable.is_file() or _sha256_file(executable) != str(artifact.get("sha256", "")):
            raise ValueError("MPV generator executable is missing or no longer matches its pinned checksum")
    arguments = config.get("arguments", [])
    outputs = config.get("expected_output_files", [])
    if not isinstance(arguments, list) or not all(isinstance(value, str) for value in arguments):
        raise ValueError("MPV generator arguments must be a list of strings")
    if (
        not isinstance(outputs, list) or not outputs
        or not all(isinstance(value, str) and Path(value).name == value for value in outputs)
    ):
        raise ValueError("MPV expected_output_files must contain one or more plain filenames")
    timeout_seconds = _positive_number(config.get("timeout_seconds", 60), "timeout_seconds")
    destination = Path(output_root).resolve() / execution_id
    if destination.exists():
        raise FileExistsError(f"MPV generator execution output already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        prefix=f".{execution_id}.", dir=destination.parent,
    ) as temporary:
        working = Path(temporary)
        for value in imported.get("artifacts", []):
            if isinstance(value, dict):
                filename = str(value.get("filename", ""))
                source = import_path.parent / filename
                if source.is_file():
                    shutil.copy2(source, working / filename)
        command_executable = executable if build_provenance_value else (working / executable.name)
        command = [str(command_executable), *arguments]
        environment = {
            key: value for key, value in os.environ.items()
            if key.upper() in {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATH", "TEMP", "TMP"}
        }
        try:
            completed = runner(
                command, cwd=working, env=environment, shell=False,
                capture_output=True, timeout=timeout_seconds, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(
                f"MPV generator exceeded timeout_seconds={timeout_seconds}"
            ) from exc
        return_code = int(completed.returncode)
        if return_code != 0:
            stderr = bytes(completed.stderr or b"").decode("utf-8", errors="replace")[-2000:]
            raise RuntimeError(f"MPV generator exited with code {return_code}: {stderr}")
        missing = [value for value in outputs if not (working / value).is_file()]
        if missing:
            raise ValueError("MPV generator did not create expected output files: " + ", ".join(missing))
        staged = working / "published"
        staged.mkdir()
        (staged / "stdout.bin").write_bytes(bytes(completed.stdout or b""))
        (staged / "stderr.bin").write_bytes(bytes(completed.stderr or b""))
        output_checksums: dict[str, str] = {}
        for filename in outputs:
            shutil.copy2(working / filename, staged / filename)
            output_checksums[filename] = _sha256_file(staged / filename)
        execution_manifest = {
            "schema_version": "1.0",
            "execution_id": execution_id,
            "source_bundle_checksum": imported.get("bundle_checksum"),
            "source_import_manifest_sha256": _sha256_file(import_path),
            "executable_role": executable_role,
            "executable_filename": executable.name,
            "executable_sha256": _sha256_file(executable),
            "arguments": arguments,
            "timeout_seconds": timeout_seconds,
            "return_code": return_code,
            "output_sha256": output_checksums,
            "stdout_sha256": _sha256_file(staged / "stdout.bin"),
            "stderr_sha256": _sha256_file(staged / "stderr.bin"),
        }
        manifest_path = staged / "execution_manifest.json"
        manifest_path.write_text(
            json.dumps(execution_manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        staged.replace(destination)
    return MpvGeneratorRun(execution_id, destination, destination / "execution_manifest.json")


def _positive_number(value: Any, field: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a positive number") from exc
    if parsed <= 0:
        raise ValueError(f"{field} must be a positive number")
    return parsed


def _write_bytes_if_new_or_identical(path: Path, content: bytes) -> None:
    if path.exists():
        if path.read_bytes() != content:
            raise FileExistsError(
                f"Refusing to overwrite different normalized MPV artifact: {path}"
            )
        return
    path.write_bytes(content)
