"""Launch the local Streamlit research application."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    app = root / "src" / "container_packing" / "web" / "streamlit_app.py"
    command = [sys.executable, "-m", "streamlit", "run", str(app), *sys.argv[1:]]
    return subprocess.call(command, cwd=root)


if __name__ == "__main__":
    raise SystemExit(main())
