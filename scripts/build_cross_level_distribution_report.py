"""Build paired Level 3--5 constraint-overhead evidence after all gates pass."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from container_packing.benchmarks.cross_level_evidence import (
    attach_profiling_evidence,
    build_cross_level_evidence,
    write_cross_level_evidence,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    for level in ("level_03", "level_04", "level_05"):
        for stratum in ("random", "stress", "prefix"):
            parser.add_argument(f"--{level}-{stratum}-run-dir", type=Path, required=True)
        parser.add_argument(f"--{level}-profile-run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    mapping = {}
    for level in ("level_03", "level_04", "level_05"):
        mapping[level] = {
            "random_distribution": getattr(args, f"{level}_random_run_dir"),
            "stress": getattr(args, f"{level}_stress_run_dir"),
            "prefix_regression": getattr(args, f"{level}_prefix_run_dir"),
        }
    report, paired = build_cross_level_evidence(mapping)
    profile_dirs = {
        level: getattr(args, f"{level}_profile_run_dir")
        for level in ("level_03", "level_04", "level_05")
    }
    report = attach_profiling_evidence(report, profile_dirs)
    write_cross_level_evidence(report, paired, args.output_dir)
    print(f"Báo cáo: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
