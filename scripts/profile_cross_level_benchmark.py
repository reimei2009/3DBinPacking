"""Profile a passed Level 3, 4 or 5 distribution benchmark."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from container_packing.benchmarks.cross_level_protocol import expected_protocol
from container_packing.benchmarks.profiling import run_benchmark_profile


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Profile a passed Level 3--5 benchmark protocol")
    parser.add_argument("--level", choices=("level_03", "level_04", "level_05"), required=True)
    parser.add_argument("--random-run-dir", type=Path, required=True)
    parser.add_argument("--stress-run-dir", type=Path, required=True)
    parser.add_argument("--prefix-run-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    result = run_benchmark_profile(
        level_id=args.level,
        random_run_dir=args.random_run_dir,
        stress_run_dir=args.stress_run_dir,
        prefix_run_dir=args.prefix_run_dir,
        expected_protocol=expected_protocol(args.level),
        report_id=f"{args.level}_distribution_v2",
        project_root=ROOT,
    )
    print(f"Trạng thái profiling: {result.status}")
    print(f"Số bài: {result.selected_case_count}")
    print(f"Số lượt chẩn đoán: {result.execution_count}")
    print(f"Thư mục profiling: {result.run_dir}")
    return 0 if result.status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
