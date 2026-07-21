"""Reproducibility metadata for experiment manifests."""

from __future__ import annotations

import hashlib
import importlib.metadata
import platform
from pathlib import Path
import subprocess
import sys


SOURCE_PATTERNS = ("src/**/*.py", "scripts/*.py", "config/**/*.yaml", "tests/**/*.py")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=True,
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unavailable"


def git_dirty(root: Path) -> bool | None:
    """Return whether tracked/untracked files exist, or None outside Git."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"], cwd=root, check=True,
            capture_output=True, text=True, timeout=5,
        )
        return bool(result.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return None


def source_tree_sha256(root: Path) -> str:
    """Hash reproducibility-relevant source/config files, including untracked files."""
    files: set[Path] = set()
    for pattern in SOURCE_PATTERNS:
        files.update(path for path in root.glob(pattern) if path.is_file())
    for name in ("pyproject.toml", "requirements.txt"):
        path = root / name
        if path.is_file():
            files.add(path)
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda value: value.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def dependency_versions() -> dict[str, str]:
    values = {}
    for package in ("numpy", "scipy", "pandas", "PyYAML"):
        try:
            values[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            values[package] = "not-installed"
    return values


def runtime_metadata(root: Path) -> dict:
    return {
        "git_commit": git_commit(root),
        "git_dirty": git_dirty(root),
        "source_tree_sha256": source_tree_sha256(root),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "dependency_versions": dependency_versions(),
        "command": [sys.executable, *sys.argv],
    }
