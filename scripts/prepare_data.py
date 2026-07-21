"""Stable generic data-preparation entrypoint for registered levels."""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from container_packing.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main(["prepare", *sys.argv[1:]]))
