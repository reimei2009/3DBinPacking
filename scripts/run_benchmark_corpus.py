"""Chạy corpus benchmark có tên và điều khiển bằng cấu hình."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from container_packing.benchmarks import run_benchmark_corpus  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--corpus", type=Path,
        default=Path("config/level_01/benchmarks/research_corpus.yaml"),
        help="Đường dẫn YAML corpus benchmark, tương đối với project root nếu không tuyệt đối",
    )
    parser.add_argument(
        "--recover-from", type=Path,
        help="Run directory of an immutable corpus artifact to recover",
    )
    parser.add_argument(
        "--rerun-failed-only", action="store_true",
        help="Reuse independently valid rows and rerun only failed rows",
    )
    args = parser.parse_args(argv)
    if bool(args.recover_from) != bool(args.rerun_failed_only):
        parser.error("--recover-from and --rerun-failed-only must be used together")
    result = run_benchmark_corpus(
        args.corpus,
        project_root=ROOT,
        recover_from=args.recover_from,
        rerun_failed_only=args.rerun_failed_only,
    )
    print("\n=== BENCHMARK CORPUS SUMMARY ===")
    preview = [
        "case_id", "group", "difficulty", "algorithm", "success_rate",
        "expectation_met_rate", "reference_kind", "objective_gap_mean_percent",
        "used_containers_mean", "total_cost_mean", "algorithm_runtime_mean_seconds",
    ]
    print(result.summary[preview].to_string(index=False))
    print(f"\nCorpus directory: {result.run_dir}")
    return 0 if result.successful else 2


if __name__ == "__main__":
    raise SystemExit(main())
