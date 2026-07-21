"""Repository-root discovery independent of the current working directory."""

from __future__ import annotations

from pathlib import Path


def find_project_root(start: str | Path | None = None) -> Path:
    origin = Path(start).resolve() if start is not None else Path(__file__).resolve()
    candidates = (origin, *origin.parents) if origin.is_dir() else origin.parents
    for candidate in candidates:
        if (candidate / "pyproject.toml").is_file() and (candidate / "config").is_dir():
            return candidate
    raise RuntimeError(f"Cannot locate repository root from {origin}")
