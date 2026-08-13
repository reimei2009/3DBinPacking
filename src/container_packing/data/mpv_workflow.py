"""Reproducible local workflow for the official MPV 3D-BPP generator.

The academic source is deliberately kept outside Git.  This module records a
TOFU lock for the official HTTPS bytes, builds the capture adapter locally, and
never publishes a partial source bundle or generator run.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from typing import Any, Callable
from urllib.request import urlopen

import yaml

from .external_sources import download_pinned_source


COMPILER_REQUIRED = "COMPILER_REQUIRED"


@dataclass(frozen=True)
class MpvBuild:
    executable_path: Path
    provenance_path: Path
    executable_sha256: str


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def load_source_lock(path: str | Path) -> dict[str, Any]:
    path = Path(path).resolve()
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"Cannot read MPV source lock {path}: {exc}") from exc
    if not isinstance(payload, dict) or str(payload.get("schema_version")) != "1.0":
        raise ValueError("MPV source lock schema_version must be '1.0'")
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 3:
        raise ValueError("MPV source lock must declare exactly three official artifacts")
    required = {"generator_source", "solver_source", "compilation_readme"}
    if {str(value.get("role")) for value in artifacts if isinstance(value, dict)} != required:
        raise ValueError("MPV source lock has invalid artifact roles")
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise ValueError("MPV source lock artifact must be a mapping")
        url = str(artifact.get("canonical_url", ""))
        expected = str(artifact.get("sha256", "")).lower()
        filename = str(artifact.get("filename", ""))
        if not url.startswith("https://hjemmesider.diku.dk/~pisinger/"):
            raise ValueError("MPV source lock only permits the official HTTPS Pisinger host")
        if Path(filename).name != filename or len(expected) != 64:
            raise ValueError("MPV source lock has invalid filename or SHA-256")
    return payload


def download_mpv_bundle(
    lock_path: str | Path, *, destination_root: str | Path,
    opener: Callable[..., object] = urlopen,
) -> Path:
    """Download all lock-pinned artifacts into one immutable source directory."""
    lock_path = Path(lock_path).resolve()
    lock = load_source_lock(lock_path)
    bundle_id = str(lock["bundle_id"])
    destination = Path(destination_root).resolve() / "sources" / bundle_id
    if destination.exists():
        for artifact in lock["artifacts"]:
            target = destination / str(artifact["filename"])
            if not target.is_file() or sha256_file(target) != str(artifact["sha256"]).lower():
                raise FileExistsError(f"Refusing to replace different MPV source artifact: {target}")
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=f".{bundle_id}.", dir=destination.parent) as temporary:
        staged = Path(temporary) / bundle_id
        staged.mkdir()
        for artifact in lock["artifacts"]:
            download_pinned_source(
                url=str(artifact["canonical_url"]),
                expected_sha256=str(artifact["sha256"]),
                destination=staged / str(artifact["filename"]),
                opener=opener,
            )
        (staged / "source_lock.json").write_text(
            json.dumps({"bundle_id": bundle_id, "lock_file": lock_path.name,
                        "checksum_policy": lock["checksum_policy"]}, indent=2) + "\n",
            encoding="utf-8",
        )
        staged.replace(destination)
    return destination


def find_c_compiler() -> str | None:
    for candidate in ("gcc", "clang", "cl"):
        if shutil.which(candidate):
            return candidate
    return None


def compiler_required_message() -> str:
    return (
        f"{COMPILER_REQUIRED}: Khong tim thay gcc/clang/cl trong PATH. "
        "Cai MinGW-w64 (MSYS2) roi mo terminal moi, kiem tra `gcc --version`, sau do chay lai."
    )


def build_mpv_capture_adapter(
    *, source_dir: str | Path, adapter_path: str | Path, build_root: str | Path,
    compiler: str | None = None, runner: Any = subprocess.run,
) -> MpvBuild:
    """Compile the local capture adapter and write build provenance."""
    source_dir = Path(source_dir).resolve()
    adapter_path = Path(adapter_path).resolve()
    compiler = compiler or find_c_compiler()
    if compiler is None:
        raise RuntimeError(compiler_required_message())
    for filename in ("test3dbpp.c", "3dbpp.c", "readme.3dbpp"):
        if not (source_dir / filename).is_file():
            raise ValueError(f"MPV source bundle is incomplete: {source_dir / filename}")
    if not adapter_path.is_file():
        raise ValueError(f"MPV capture adapter does not exist: {adapter_path}")
    source_digest = sha256()
    for filename in ("test3dbpp.c", "3dbpp.c", "readme.3dbpp"):
        source_digest.update(filename.encode("ascii") + b"\0" + sha256_file(source_dir / filename).encode("ascii") + b"\0")
    bundle_checksum = source_digest.hexdigest()
    build_dir = Path(build_root).resolve() / f"mpv_capture_{bundle_checksum[:12]}"
    executable = build_dir / ("mpv_capture.exe" if os.name == "nt" else "mpv_capture")
    provenance = build_dir / "build_provenance.json"
    if executable.is_file() and provenance.is_file():
        payload = json.loads(provenance.read_text(encoding="utf-8"))
        if payload.get("source_bundle_checksum") == bundle_checksum and payload.get("executable_sha256") == sha256_file(executable):
            return MpvBuild(executable, provenance, sha256_file(executable))
        raise FileExistsError(f"Refusing to replace different MPV build: {build_dir}")
    build_dir.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".mpv-build.", dir=build_dir.parent) as temporary:
        staged = Path(temporary)
        output = staged / executable.name
        command = ([compiler, "-ansi", "-O2", "-o", str(output), str(source_dir / "test3dbpp.c"), str(adapter_path), "-lm"]
                   if compiler != "cl" else [compiler, "/TC", "/O2", f"/Fe{output}", str(source_dir / "test3dbpp.c"), str(adapter_path)])
        completed = runner(command, capture_output=True, text=True, check=False)
        if int(completed.returncode) != 0 or not output.is_file():
            raise RuntimeError(f"MPV capture build failed: {(completed.stderr or completed.stdout)[-2000:]}")
        version = runner([compiler, "--version"], capture_output=True, text=True, check=False)
        data = {
            "schema_version": "1.0", "compiler": compiler,
            "compiler_version": (version.stdout or version.stderr or "").splitlines()[0:1],
            "build_command": command, "source_bundle_checksum": bundle_checksum,
            "source_file_sha256": {name: sha256_file(source_dir / name) for name in ("test3dbpp.c", "3dbpp.c", "readme.3dbpp")},
            "adapter_sha256": sha256_file(adapter_path), "executable_filename": output.name,
            "executable_sha256": sha256_file(output),
        }
        (staged / "build_provenance.json").write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        staged.replace(build_dir)
    return MpvBuild(executable, provenance, sha256_file(executable))
