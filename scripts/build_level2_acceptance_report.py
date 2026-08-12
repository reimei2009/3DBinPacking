"""Tạo report nghiệm thu Level 2 từ các benchmark run bất biến."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from container_packing.benchmarks.level2_acceptance import (  # noqa: E402
    build_level2_acceptance_report,
    write_level2_acceptance_report,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fleet-500-run", type=Path, required=True)
    parser.add_argument("--fleet-5000-run", type=Path, required=True)
    parser.add_argument("--scale-20-300-run", type=Path, required=True)
    parser.add_argument("--mpv-run", type=Path)
    parser.add_argument(
        "--output-prefix", type=Path,
        default=Path("docs/reports/manual/level_02_acceptance_20260812"),
    )
    args = parser.parse_args(argv)
    report = build_level2_acceptance_report(
        internal_runs=(
            ("fleet_500", args.fleet_500_run),
            ("fleet_5000", args.fleet_5000_run),
            ("scale_20_300", args.scale_20_300_run),
        ),
        mpv_run=args.mpv_run,
    )
    json_path, markdown_path = write_level2_acceptance_report(report, args.output_prefix)
    print(f"Status : {report['status']}")
    print(f"JSON   : {json_path}")
    print(f"Report : {markdown_path}")
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
