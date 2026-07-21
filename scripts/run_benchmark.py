"""Run a reproducible local benchmark matrix across registered algorithms."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from container_packing.algorithms.registry import list_algorithms  # noqa: E402
from container_packing.benchmarks import run_benchmark  # noqa: E402
from container_packing.levels.registry import get_level  # noqa: E402


def _positive(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _non_negative(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--level", default="level_01")
    parser.add_argument("--algorithms", nargs="+")
    parser.add_argument("--item-counts", nargs="+", type=_positive, default=[10, 20])
    parser.add_argument("--container-counts", nargs="+", type=_positive, default=[3, 5])
    parser.add_argument("--seeds", nargs="+", type=_non_negative, help="Distinct random seeds; defaults to project.random_seed")
    parser.add_argument("--repeats", type=_positive, default=1, help="Timing repetitions for each seed")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--environment", choices=("local", "colab", "kaggle"), default="local")
    args = parser.parse_args(argv)
    level = get_level(args.level)
    algorithms = args.algorithms or [value.algorithm_id for value in list_algorithms(level_id=level.level_id)]
    result = run_benchmark(
        level_id=level.level_id, algorithm_ids=algorithms,
        item_counts=args.item_counts, container_counts=args.container_counts,
        repeats=args.repeats, seeds=args.seeds, config_path=args.config, environment=args.environment,
    )
    print("\n=== BENCHMARK SUMMARY ===")
    preview_columns = [
        "level", "algorithm", "item_count", "container_count", "run_count", "seed_count",
        "success_rate", "objective_mean", "objective_std", "used_containers_mean",
        "used_containers_std", "total_cost_mean", "total_cost_std", "distinct_solution_count",
        "algorithm_runtime_mean_seconds",
    ]
    print(result.summary[preview_columns].to_string(index=False))
    print(f"\nBenchmark directory: {result.run_dir}")
    return 0 if result.successful else 2


if __name__ == "__main__":
    raise SystemExit(main())
