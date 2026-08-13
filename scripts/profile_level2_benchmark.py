"""Profile selected Level 2 V2 cases after the three evidence gates pass."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from container_packing.benchmarks.profiling import run_level2_benchmark_profile  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Profile a bounded diagnostic subset of passed Level 2 V2 benchmark runs."
        )
    )
    parser.add_argument("--random-run-dir", type=Path, required=True)
    parser.add_argument("--stress-run-dir", type=Path, required=True)
    parser.add_argument("--prefix-run-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    result = run_level2_benchmark_profile(
        random_run_dir=args.random_run_dir,
        stress_run_dir=args.stress_run_dir,
        prefix_run_dir=args.prefix_run_dir,
        project_root=ROOT,
    )
    print(f"Trạng thái profiling : {result.status}")
    print(f"Số bài               : {result.selected_case_count}")
    print(f"Số lượt chẩn đoán    : {result.execution_count}")
    print(f"Thư mục profiling    : {result.run_dir}")
    return 0 if result.status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
