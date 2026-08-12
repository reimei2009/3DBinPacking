"""Mở khóa profile web Level 2 lớn sau khi benchmark gate thủ công đạt yêu cầu."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from container_packing.large_scale_web_gate import qualify_large_scale_web_profile  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--maximum-peak-memory-gb", type=float, default=8.0)
    args = parser.parse_args(argv)
    result = qualify_large_scale_web_profile(
        (ROOT / args.run_dir).resolve(),
        ROOT / "data/interim/synthetic/level_02_solver_research_i20000_f5000_v1/generation_manifest.json",
        ROOT / "data/interim/synthetic/level_02_solver_research_i20000_f5000_v1/web_qualification.json",
        maximum_peak_rss_bytes=int(args.maximum_peak_memory_gb * 1024**3),
    )
    print("\n=== LEVEL 2 LARGE WEB GATE ===")
    print(f"Qualified : {result.qualified}")
    print(f"Run       : {result.run_id}")
    print(f"Scales    : {', '.join(str(value) for value in result.item_counts)}")
    print(f"Gate file : {result.gate_path}")
    print("Restart Streamlit to make the source visible.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
