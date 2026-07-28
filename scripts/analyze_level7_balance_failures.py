"""Diagnose completed Level 7 benchmark runs without invoking a solver.

The script follows the source-run paths recorded by ``benchmark/results.csv``.
It is deliberately diagnostic only: an invalid candidate remains invalid and
its reported cost/container count is never promoted to an objective result.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


AXES = (
    ("longitudinal", "signed_longitudinal_offset_ratio", "max_longitudinal_offset_ratio"),
    ("lateral", "signed_lateral_offset_ratio", "max_lateral_offset_ratio"),
)


def analyse_benchmark(benchmark_dir: Path) -> dict[str, Any]:
    """Return a compact, reproducible diagnosis for invalid Level 7 source runs."""
    benchmark_dir = benchmark_dir.resolve()
    results_path = benchmark_dir / "benchmark" / "results.csv"
    if not results_path.is_file():
        raise FileNotFoundError(f"Benchmark results are missing: {results_path}")

    with results_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    invalid_rows = [row for row in rows if row.get("status") == "INVALID_SOLUTION"]
    diagnoses = [_diagnose_row(row, benchmark_dir) for row in invalid_rows]
    by_scenario: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for diagnosis in diagnoses:
        by_scenario[diagnosis["scenario_id"]].append(diagnosis)

    return {
        "schema_version": "1.0",
        "level": "level_07",
        "benchmark_run_dir": str(benchmark_dir),
        "source_run_count": len(rows),
        "invalid_run_count": len(diagnoses),
        "invalid_runs": diagnoses,
        "scenario_summary": {
            scenario_id: _scenario_summary(values)
            for scenario_id, values in sorted(by_scenario.items())
        },
        "interpretation": {
            "candidate_metrics_are_diagnostic_only": True,
            "repairability_not_proven": True,
            "next_decision_input": (
                "Use the worst axis/container excess and repair termination reason to "
                "choose a targeted partial-repack neighborhood; do not compare invalid "
                "candidate costs with valid objectives."
            ),
        },
    }


def compare_analyses(
    baseline: dict[str, Any], current: dict[str, Any]
) -> list[dict[str, Any]]:
    """Compare invalid-run diagnostics using scenario and algorithm as identity."""
    old = {
        (value["scenario_id"], value["algorithm"]): value
        for value in baseline["invalid_runs"]
    }
    rows: list[dict[str, Any]] = []
    for value in current["invalid_runs"]:
        key = (value["scenario_id"], value["algorithm"])
        previous = old.get(key)
        current_excess = (
            value["dominant_failure"]["excess_ratio"]
            if value["dominant_failure"] else 0.0
        )
        previous_excess = (
            previous["dominant_failure"]["excess_ratio"]
            if previous and previous["dominant_failure"] else None
        )
        rows.append({
            "scenario_id": key[0],
            "algorithm": key[1],
            "previous_max_excess_ratio": previous_excess,
            "current_max_excess_ratio": current_excess,
            "max_excess_delta": (
                None if previous_excess is None
                else current_excess - previous_excess
            ),
            "previous_runtime_seconds": (
                None if previous is None
                else previous["algorithm_runtime_seconds"]
            ),
            "current_runtime_seconds": value["algorithm_runtime_seconds"],
            "current_repair_stop": value["repair"]["termination_reason"],
            "current_lns_stop": value["lns"]["termination_reason"],
        })
    return rows


def _diagnose_row(row: dict[str, str], benchmark_dir: Path) -> dict[str, Any]:
    source_dir = _resolve_source_run_dir(row["experiment_run_dir"], benchmark_dir)
    solver = _read_json(source_dir / "solver" / "solver_summary.json")
    balance = _read_json(source_dir / "validation" / "balance_validation.json")
    violations = [
        violation
        for record in balance.get("records", [])
        for violation in _axis_violations(record)
    ]
    violations.sort(key=lambda value: (-value["excess_ratio"], value["container_id"], value["axis"]))
    contributor_evidence = _contributor_evidence(source_dir, violations)
    classification = _classify_failure(solver, violations, contributor_evidence)
    return {
        "scenario_id": row["scenario_id"],
        "algorithm": row["algorithm"],
        "item_count": int(row["item_count"]),
        "container_count": int(row["container_count"]),
        "input_fingerprint": row["input_fingerprint"],
        "source_run_dir": str(source_dir),
        "algorithm_runtime_seconds": float(solver.get("algorithm_runtime_seconds", 0.0)),
        "used_container_count_diagnostic": int(solver.get("n_containers_used", row["used_container_count"])),
        "candidate_objective_diagnostic": solver.get("candidate_objective_value"),
        "balance_failure_reason": solver.get("balance_failure_reason"),
        "repair": {
            "phase": solver.get("balance_repair_phase"),
            "termination_reason": solver.get("balance_repair_termination_reason"),
            "candidates_evaluated": solver.get("balance_repair_candidates_evaluated"),
            "accepted_moves": solver.get("balance_repair_accepted_moves", []),
            "initial_max_violation": solver.get("balance_repair_initial_max_violation"),
            "final_max_violation": solver.get("balance_repair_final_max_violation"),
        },
        "lns": {
            "termination_reason": solver.get("balance_lns_termination_reason"),
            "candidates_evaluated": solver.get("balance_lns_candidates_evaluated"),
            "affected_container_ids": solver.get("balance_lns_affected_container_ids", []),
            "destroyed_item_ids": solver.get("balance_lns_destroyed_item_ids", []),
        },
        "balance_violations": violations,
        "dominant_failure": violations[0] if violations else None,
        "contributor_evidence": contributor_evidence,
        "repair_classification": classification,
    }


def _axis_violations(record: dict[str, Any]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for axis, signed_key, limit_key in AXES:
        signed = float(record[signed_key])
        limit = float(record[limit_key])
        excess = abs(signed) - limit
        if excess > 0.0:
            values.append({
                "container_id": record["container_id"],
                "axis": axis,
                "signed_offset_ratio": signed,
                "limit_ratio": limit,
                "excess_ratio": excess,
                "needed_mass_shift_direction": _direction(axis, signed),
            })
    return values


def _contributor_evidence(
    source_dir: Path, violations: list[dict[str, Any]], limit: int = 8
) -> list[dict[str, Any]]:
    placements_path = source_dir / "solution" / "placements.csv"
    stacks_path = source_dir / "solution" / "stacks.csv"
    if not placements_path.is_file():
        return []
    placements = _read_csv(placements_path)
    supporters: set[str] = set()
    if stacks_path.is_file():
        for row in _read_csv(stacks_path):
            parent = row.get("direct_parent_item_id", "").strip()
            if parent:
                supporters.add(parent)
    evidence: list[dict[str, Any]] = []
    for violation in violations:
        axis = violation["axis"]
        direction = violation["needed_mass_shift_direction"]
        coordinate = "y_mm" if axis == "lateral" else "x_mm"
        dimension = "width_mm" if axis == "lateral" else "length_mm"
        values = [
            row for row in placements
            if row["container_id"] == violation["container_id"]
        ]
        centers = {
            row["item_id"]: float(row[coordinate]) + float(row[dimension]) / 2.0
            for row in values
        }
        target_side = max if direction in {"increase_x", "increase_y"} else min
        ordered = sorted(
            values,
            key=lambda row: (
                target_side(centers.values()) - centers[row["item_id"]]
                if direction in {"increase_x", "increase_y"}
                else centers[row["item_id"]] - target_side(centers.values()),
                -float(row["weight_kg"]),
                row["item_id"],
            ),
            reverse=True,
        )
        candidates = [{
            "item_id": row["item_id"],
            "weight_kg": float(row["weight_kg"]),
            "axis_center_mm": centers[row["item_id"]],
            "is_supporter": row["item_id"] in supporters,
            "recommended_operator": (
                "support_closure_partial_repack"
                if row["item_id"] in supporters else "leaf_relocation_or_transfer"
            ),
        } for row in ordered[:limit]]
        evidence.append({
            "container_id": violation["container_id"],
            "axis": axis,
            "needed_mass_shift_direction": direction,
            "candidate_contributors": candidates,
            "leaf_candidate_count": sum(not value["is_supporter"] for value in candidates),
            "supporter_candidate_count": sum(value["is_supporter"] for value in candidates),
        })
    return evidence


def _classify_failure(
    solver: dict[str, Any],
    violations: list[dict[str, Any]],
    contributor_evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    leaf_count = sum(value["leaf_candidate_count"] for value in contributor_evidence)
    supporter_count = sum(value["supporter_candidate_count"] for value in contributor_evidence)
    if leaf_count:
        category = "targeted_local_repair_candidate"
        operator = "directional_leaf_relocation_then_transfer"
    elif supporter_count:
        category = "partial_repack_required"
        operator = "directional_support_closure_destroy_repack"
    else:
        category = "extra_container_candidate_after_fixed_subset_search"
        operator = "controlled_one_extra_container"
    return {
        "category": category,
        "recommended_operator": operator,
        "repairability_proven": False,
        "evidence": {
            "violating_axis_count": len(violations),
            "leaf_contributor_candidates": leaf_count,
            "supporter_contributor_candidates": supporter_count,
            "local_repair_stop": solver.get("balance_repair_termination_reason"),
            "lns_stop": solver.get("balance_lns_termination_reason"),
            "accepted_move_count": len(solver.get("balance_repair_accepted_moves", [])),
        },
    }


def _direction(axis: str, signed_offset: float) -> str:
    if axis == "lateral":
        return "increase_y" if signed_offset < 0 else "decrease_y"
    return "increase_x" if signed_offset < 0 else "decrease_x"


def _scenario_summary(values: list[dict[str, Any]]) -> dict[str, Any]:
    dominant = [value["dominant_failure"] for value in values if value["dominant_failure"]]
    return {
        "invalid_algorithm_count": len(values),
        "algorithms": [value["algorithm"] for value in values],
        "dominant_axes": sorted({value["axis"] for value in dominant}),
        "maximum_excess_ratio": max((value["excess_ratio"] for value in dominant), default=0.0),
        "repair_termination_reasons": sorted({
            str(value["repair"]["termination_reason"]) for value in values
        }),
        "lns_termination_reasons": sorted({
            str(value["lns"]["termination_reason"]) for value in values
        }),
    }


def write_report(document: dict[str, Any], output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "level_07_balance_failure_analysis.json"
    markdown_path = output_dir / "level_07_balance_failure_analysis.md"
    json_path.write_text(json.dumps(document, indent=2), encoding="utf-8")
    lines = ["# Level 7 balance failure analysis", "", f"Invalid source runs: {document['invalid_run_count']}", ""]
    for scenario_id, summary in document["scenario_summary"].items():
        lines.extend([
            f"## {scenario_id}", "",
            f"- Algorithms: {', '.join(summary['algorithms'])}",
            f"- Dominant axes: {', '.join(summary['dominant_axes']) or 'none'}",
            f"- Maximum excess ratio: {summary['maximum_excess_ratio']:.6f}",
            f"- Local repair stops: {', '.join(summary['repair_termination_reasons'])}",
            f"- LNS stops: {', '.join(summary['lns_termination_reasons'])}", "",
        ])
    lines.extend(["## Per-run repair classification", ""])
    for run in document["invalid_runs"]:
        classification = run["repair_classification"]
        lines.append(
            f"- `{run['scenario_id']}` / `{run['algorithm']}`: "
            f"`{classification['category']}` -> `{classification['recommended_operator']}`"
        )
    lines.append("")
    if document.get("before_after_comparison"):
        lines.extend(["## Before/after comparison", ""])
        for row in document["before_after_comparison"]:
            delta = row["max_excess_delta"]
            delta_text = "n/a" if delta is None else f"{delta:+.6f}"
            lines.append(
                f"- `{row['scenario_id']}` / `{row['algorithm']}`: "
                f"max-excess delta `{delta_text}`, runtime "
                f"`{row['current_runtime_seconds']:.3f}s`"
            )
        lines.append("")
    lines.extend([
        "## Interpretation", "",
        "Candidate container counts and costs for invalid runs are diagnostics only; they are not comparable objectives.",
        "The report does not claim a failure is infeasible. It identifies the first axis/container to target in the next repair experiment.",
    ])
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, markdown_path


def _resolve_source_run_dir(raw_path: str, benchmark_dir: Path) -> Path:
    source = Path(raw_path)
    if source.is_absolute():
        return source
    root = benchmark_dir.parents[3]
    return (root / source).resolve()


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Required source-run artifact is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-dir", type=Path, required=True)
    parser.add_argument("--baseline-benchmark-dir", type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    document = analyse_benchmark(args.benchmark_dir)
    if args.baseline_benchmark_dir:
        baseline = analyse_benchmark(args.baseline_benchmark_dir)
        document["before_after_comparison"] = compare_analyses(
            baseline, document
        )
    output_dir = args.output_dir or args.benchmark_dir / "reports"
    json_path, markdown_path = write_report(document, output_dir)
    print(f"Invalid source runs: {document['invalid_run_count']}")
    for scenario_id, summary in document["scenario_summary"].items():
        print(f"{scenario_id}: axes={summary['dominant_axes']}, max_excess={summary['maximum_excess_ratio']:.6f}")
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
