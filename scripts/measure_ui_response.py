"""Measure versioned warm Streamlit rerun latency without invoking a solver."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from container_packing.productization.ui_latency import (  # noqa: E402
    run_streamlit_ui_response_measurement,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--level", default="level_02")
    parser.add_argument("--profile", default="items_1000_fleet_500_t10")
    parser.add_argument("--warmups", type=int, default=3)
    parser.add_argument("--samples", type=int, default=30)
    args = parser.parse_args(argv)
    run_dir = run_streamlit_ui_response_measurement(
        root=ROOT,
        level_id=args.level,
        profile_id=args.profile,
        warmups=args.warmups,
        samples=args.samples,
    )
    print(f"UI response evidence: {run_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
