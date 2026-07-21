"""Run a config-driven, multi-seed algorithm parameter sweep."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from container_packing.sweeps import run_parameter_sweep  # noqa: E402


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
    parser.add_argument(
        "--config", type=Path,
        default=Path("config/level_01/sweeps/extreme_point_simulated_annealing_local.yaml"),
    )
    parser.add_argument("--item-counts", nargs="+", type=_positive)
    parser.add_argument("--container-counts", nargs="+", type=_positive)
    parser.add_argument("--seeds", nargs="+", type=_non_negative)
    parser.add_argument("--repeats", type=_positive)
    args = parser.parse_args(argv)
    result = run_parameter_sweep(
        args.config, seeds=args.seeds, repeats=args.repeats,
        item_counts=args.item_counts, container_counts=args.container_counts,
    )
    preview_columns = [
        "rank", "parameter_set_id",
        *[column for column in result.parameter_sets.columns if column != "parameter_set_id"],
        "success_rate", "objective_mean", "used_containers_mean", "total_cost_mean",
        "occupied_bounding_volume_mean_mm3", "occupied_bounding_volume_std_mm3",
        "distinct_solution_count", "algorithm_runtime_mean_seconds",
    ]
    print("\n=== PARAMETER SWEEP RANKING ===")
    print(result.ranking[preview_columns].to_string(index=False))
    print(f"\nSweep directory: {result.run_dir}")
    return 0 if result.successful else 2


if __name__ == "__main__":
    raise SystemExit(main())
