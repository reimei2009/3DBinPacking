"""Build the versioned Level 7 primary/comparator acceptance report.

This command is intentionally read-only with respect to experiment outputs. It
consumes two completed benchmark directories and writes a compact Markdown
report to an explicitly selected documentation path.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path


PRIMARY = "extreme_point_best_fit_balance"
COMPARATOR = "extreme_point_ffd_balance"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--primary-benchmark-dir", type=Path, required=True)
    parser.add_argument("--comparator-benchmark-dir", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path,
        default=Path("docs/reports/manual/level_07_scale_baseline.md"),
    )
    parser.add_argument("--max-runtime-seconds", type=float, default=45.0)
    args = parser.parse_args(argv)

    primary = _load_rows(args.primary_benchmark_dir, PRIMARY)
    comparator = _load_rows(args.comparator_benchmark_dir, COMPARATOR)
    primary_records = _enrich(primary)
    comparator_records = _enrich(comparator)
    primary_gates = _primary_gates(primary_records, args.max_runtime_seconds)
    accepted = all(primary_gates.values())

    lines = [
        "# Level 7 scale baseline",
        "",
        "This is an R&D balance baseline. The synthetic COG band is not a "
        "vehicle-certification standard.",
        "",
        "## Promotion gates",
        "",
        *[
            f"- [{'x' if value else ' '}] `{key}`"
            for key, value in primary_gates.items()
        ],
        "",
        f"**Primary acceptance:** {'PASS' if accepted else 'FAIL'}",
        "",
        "## Best Fit primary",
        "",
        _table(primary_records),
        "",
        "## FFD fast comparator",
        "",
        "Comparator failures are recorded but do not block primary promotion.",
        "",
        _table(comparator_records),
        "",
        "## Outcome contract",
        "",
        "- `VALID_FIXED_CONTAINER`",
        "- `VALID_WITH_ONE_EXTRA_CONTAINER`",
        "- `NO_VALID_BALANCED_SOLUTION_WITHIN_BUDGET`",
        "",
        "Invalid candidates have no objective value and are excluded from "
        "objective comparisons.",
    ]
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Level 7 baseline report: {output}")
    print(f"Primary acceptance: {'PASS' if accepted else 'FAIL'}")
    return 0 if accepted else 2


def _load_rows(directory: Path, expected_algorithm: str) -> list[dict[str, str]]:
    path = directory.resolve() / "benchmark" / "results.csv"
    if not path.is_file():
        raise FileNotFoundError(f"Missing benchmark results: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"Benchmark contains no source runs: {path}")
    algorithms = {row["algorithm"] for row in rows}
    if algorithms != {expected_algorithm}:
        raise ValueError(
            f"{path} must contain only {expected_algorithm}; got {sorted(algorithms)}"
        )
    return rows


def _enrich(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for row in rows:
        run_dir = Path(row["experiment_run_dir"]).resolve()
        solver = _json(run_dir / "solver" / "solver_summary.json")
        balance_path = run_dir / "validation" / "balance_validation.json"
        balance = _json(balance_path)
        margins = [
            min(
                float(record["max_longitudinal_offset_ratio"])
                - float(record["absolute_longitudinal_offset_ratio"]),
                float(record["max_lateral_offset_ratio"])
                - float(record["absolute_lateral_offset_ratio"]),
            )
            for record in balance.get("records", [])
        ]
        records.append({
            "scenario": row["scenario_id"],
            "repeat": int(row["repeat"]),
            "success": row["success"].strip().lower() == "true",
            "validation": row["validation_valid"].strip().lower() == "true",
            "objective": _optional_float(row["objective_value"]),
            "containers": int(row["used_container_count"]),
            "level6_baseline_containers": int(
                solver.get("balance_repair_initial_container_count",
                           row["used_container_count"])
            ),
            "runtime": float(row["algorithm_runtime_seconds"]),
            "signature": row["placement_signature"],
            "cog_checksum": _sha256(balance_path),
            "minimum_cog_margin": min(margins) if margins else None,
            "outcome": solver.get("balance_outcome_class"),
        })
    return records


def _primary_gates(
    records: list[dict[str, object]], max_runtime_seconds: float
) -> dict[str, bool]:
    grouped: dict[str, list[dict[str, object]]] = defaultdict(list)
    for record in records:
        grouped[str(record["scenario"])].append(record)
    return {
        "six_frozen_profiles_present": len(grouped) == 6,
        "two_repeats_per_profile": all(len(values) == 2 for values in grouped.values()),
        "all_runs_independently_valid": all(
            value["success"] and value["validation"] for value in records
        ),
        "invalid_runs_have_no_objective": all(
            value["objective"] is not None
            if value["validation"] else value["objective"] is None
            for value in records
        ),
        "runtime_within_45_seconds": all(
            float(value["runtime"]) <= max_runtime_seconds for value in records
        ),
        "container_count_within_level6_plus_one": all(
            int(value["containers"])
            <= int(value["level6_baseline_containers"]) + 1
            for value in records
        ),
        "deterministic_signature_objective_and_cog": all(
            len({value["signature"] for value in values}) == 1
            and len({value["objective"] for value in values}) == 1
            and len({value["cog_checksum"] for value in values}) == 1
            for values in grouped.values()
        ),
        "outcome_class_is_explicit": all(
            value["outcome"] in {
                "VALID_FIXED_CONTAINER",
                "VALID_WITH_ONE_EXTRA_CONTAINER",
                "NO_VALID_BALANCED_SOLUTION_WITHIN_BUDGET",
            }
            for value in records
        ),
    }


def _table(records: list[dict[str, object]]) -> str:
    header = (
        "| Scenario | Repeat | Valid | Containers | Objective | Runtime (s) | "
        "Min COG margin | Outcome |\n"
        "|---|---:|:---:|---:|---:|---:|---:|---|"
    )
    rows = []
    for value in sorted(records, key=lambda row: (str(row["scenario"]), int(row["repeat"]))):
        objective = "—" if value["objective"] is None else f"{float(value['objective']):.3f}"
        margin = (
            "—" if value["minimum_cog_margin"] is None
            else f"{float(value['minimum_cog_margin']):.6f}"
        )
        rows.append(
            f"| {value['scenario']} | {value['repeat']} | "
            f"{'yes' if value['validation'] else 'no'} | {value['containers']} | "
            f"{objective} | {float(value['runtime']):.3f} | {margin} | "
            f"{value['outcome']} |"
        )
    return "\n".join([header, *rows])


def _json(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Missing required Level 7 artifact: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _optional_float(value: str) -> float | None:
    return None if not value.strip() else float(value)


if __name__ == "__main__":
    raise SystemExit(main())
