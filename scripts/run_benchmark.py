"""Run a reproducible local benchmark matrix across registered algorithms."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from container_packing.algorithms.registry import list_algorithms  # noqa: E402
from container_packing.benchmarks import run_benchmark  # noqa: E402
from container_packing.benchmarks.suites import load_benchmark_suite  # noqa: E402
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
    parser.add_argument("--level")
    parser.add_argument("--algorithms", nargs="+")
    parser.add_argument("--item-counts", nargs="+", type=_positive, default=[10, 20])
    parser.add_argument("--container-counts", nargs="+", type=_positive, default=[3, 5])
    parser.add_argument("--seeds", nargs="+", type=_non_negative, help="Distinct random seeds; defaults to project.random_seed")
    parser.add_argument("--repeats", type=_positive, help="Timing repetitions for each seed")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--environment", choices=("local", "colab", "kaggle"))
    parser.add_argument(
        "--suite", type=Path,
        help="Named YAML comparison protocol. Its scenarios are shared by all algorithms.",
    )
    args = parser.parse_args(argv)
    suite = load_benchmark_suite(args.suite) if args.suite else None
    if suite and args.level and args.level != suite.level_id:
        parser.error("--level must match the level_id declared by --suite")
    level = get_level(suite.level_id if suite else (args.level or "level_01"))
    algorithms = args.algorithms or (list(suite.algorithms) if suite else [
        value.algorithm_id for value in list_algorithms(level_id=level.level_id)
    ])
    result = run_benchmark(
        level_id=level.level_id, algorithm_ids=algorithms,
        item_counts=args.item_counts, container_counts=args.container_counts,
        repeats=args.repeats if args.repeats is not None else (suite.repeats if suite else 1),
        seeds=args.seeds if args.seeds is not None else (suite.seeds if suite else None),
        config_path=args.config or (suite.config_path if suite else None),
        environment=args.environment or (suite.environment if suite else "local"),
        scenarios=suite.scenarios if suite else None,
        suite_id=suite.suite_id if suite else None,
        suite_source_path=suite.source_path if suite else None,
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
