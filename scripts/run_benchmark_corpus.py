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
    args = parser.parse_args(argv)
    result = run_benchmark_corpus(args.corpus, project_root=ROOT)
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
