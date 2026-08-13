"""Tải nguồn benchmark ngoài với URL và SHA-256 được khóa rõ ràng."""

from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlparse
from urllib.request import urlopen


def download_pinned_source(
    *,
    url: str,
    expected_sha256: str,
    destination: Path,
    opener: Callable[..., object] = urlopen,
    timeout_seconds: float = 60.0,
) -> str:
    """Tải một artifact HTTPS, kiểm checksum rồi mới publish atomically."""
    if urlparse(url).scheme != "https":
        raise ValueError("External benchmark URL must use HTTPS")
    expected = expected_sha256.strip().lower()
    if len(expected) != 64 or any(value not in "0123456789abcdef" for value in expected):
        raise ValueError("expected_sha256 must contain exactly 64 hexadecimal characters")
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    digest = sha256()
    temporary_path: Path | None = None
    try:
        with opener(url, timeout=timeout_seconds) as response, NamedTemporaryFile(
            mode="wb", delete=False, dir=destination.parent,
            prefix=f".{destination.name}.", suffix=".download",
        ) as handle:
            temporary_path = Path(handle.name)
            while chunk := response.read(1024 * 1024):
                digest.update(chunk)
                handle.write(chunk)
        actual = digest.hexdigest()
        if actual != expected:
            raise ValueError(
                f"SHA-256 mismatch for {url}: expected {expected}, got {actual}"
            )
        temporary_path.replace(destination)
        temporary_path = None
        return actual
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def import_pinned_local_source(
    *, source: Path, expected_sha256: str, destination: Path,
) -> str:
    """Verify a caller-supplied local artifact and publish it atomically.

    The checksum must come from outside this function.  Existing destinations
    are accepted only when they already contain the exact pinned bytes.
    """
    expected = expected_sha256.strip().lower()
    if len(expected) != 64 or any(value not in "0123456789abcdef" for value in expected):
        raise ValueError("expected_sha256 must contain exactly 64 hexadecimal characters")
    source = source.resolve()
    destination = destination.resolve()
    if not source.is_file():
        raise ValueError(f"Local external source does not exist: {source}")
    digest = sha256()
    with source.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual != expected:
        raise ValueError(
            f"SHA-256 mismatch for {source}: expected {expected}, got {actual}"
        )
    if destination.exists():
        existing = sha256(destination.read_bytes()).hexdigest()
        if existing != expected:
            raise FileExistsError(
                f"Refusing to overwrite different external artifact: {destination}"
            )
        return actual
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with source.open("rb") as input_handle, NamedTemporaryFile(
            mode="wb", delete=False, dir=destination.parent,
            prefix=f".{destination.name}.", suffix=".import",
        ) as output_handle:
            temporary_path = Path(output_handle.name)
            while chunk := input_handle.read(1024 * 1024):
                output_handle.write(chunk)
        temporary_path.replace(destination)
        temporary_path = None
        return actual
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
