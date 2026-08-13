"""Tạo report evidence từ một canonical benchmark Level 2 đã persist."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from container_packing.benchmarks.canonical_evidence import (  # noqa: E402
    build_canonical_benchmark_evidence,
    write_canonical_benchmark_evidence,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument(
        "--output-prefix",
        type=Path,
        default=Path("docs/reports/manual/level_02_canonical_benchmark_20260813"),
    )
    args = parser.parse_args(argv)
    report = build_canonical_benchmark_evidence(args.run_dir)
    json_path, markdown_path = write_canonical_benchmark_evidence(
        report, args.output_prefix,
    )
    # Giữ CLI an toàn trên Windows PowerShell còn dùng code page cp1252.
    print(f"Status : {report['status']}")
    print(f"JSON   : {json_path}")
    print(f"Report : {markdown_path}")
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
