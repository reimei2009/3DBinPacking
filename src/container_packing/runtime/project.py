"""Repository-root discovery independent of the current working directory."""

from __future__ import annotations

import os
from pathlib import Path


def find_project_root(start: str | Path | None = None) -> Path:
    """Locate the repository assets required by a configured experiment.

    Installed packages live under ``site-packages`` while tracked configuration and
    data remain in the application checkout (for example ``/app`` in Render).
    Therefore module-file discovery alone is insufficient in a container.  An
    explicit environment override is preferred, followed by the supplied origin
    and the process working directory for local editable installs.
    """
    origins: list[Path] = []
    configured_root = os.environ.get("CONTAINER_PACKING_PROJECT_ROOT")
    if configured_root:
        origins.append(Path(configured_root).expanduser())
    if start is not None:
        origins.append(Path(start))
    else:
        origins.append(Path(__file__))
    origins.append(Path.cwd())

    inspected: list[Path] = []
    for origin in origins:
        resolved = origin.resolve()
        candidates = (resolved, *resolved.parents) if resolved.is_dir() else resolved.parents
        for candidate in candidates:
            if candidate in inspected:
                continue
            inspected.append(candidate)
            if (candidate / "pyproject.toml").is_file() and (candidate / "config").is_dir():
                return candidate
    checked = ", ".join(str(path) for path in origins)
    raise RuntimeError(f"Cannot locate repository root; checked from: {checked}")
