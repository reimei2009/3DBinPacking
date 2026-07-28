"""Assess one completed Level 7 run without re-running its solver."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--max-runtime-seconds", type=float, default=45.0)
    parser.add_argument("--expected-max-containers", type=int)
    args = parser.parse_args(argv)
    run_dir = args.run_dir.resolve()
    manifest = _read(run_dir / "manifest.json")
    solver = _read(run_dir / "solver" / "solver_summary.json")
    balance = _read(run_dir / "validation" / "balance_validation.json")
    if manifest.get("level") != "level_07":
        raise ValueError("--run-dir must be a Level 7 run directory")
    runtime = float(solver.get("algorithm_runtime_seconds", 0.0))
    used = _used_container_count(run_dir / "solution" / "containers.csv")
    valid = bool(balance.get("valid", False))
    objective = solver.get("objective_value")
    phase = solver.get("balance_repair_phase")
    outcome_class = solver.get("balance_outcome_class")
    gates = {
        "independent_balance_valid": valid,
        "all_used_containers_balanced": not balance.get("violations"),
        "objective_only_when_valid": (objective is not None) if valid else objective is None,
        "runtime_within_sla": runtime <= args.max_runtime_seconds,
        "container_target_met": (
            True if args.expected_max_containers is None else used <= args.expected_max_containers
        ),
        "search_evidence_present": (
            phase == "baseline_valid"
            or "balance_lns_termination_reason" in solver
        ),
        "outcome_class_consistent": (
            outcome_class in {
                "VALID_FIXED_CONTAINER", "VALID_WITH_ONE_EXTRA_CONTAINER"
            }
            if valid
            else outcome_class == "NO_VALID_BALANCED_SOLUTION_WITHIN_BUDGET"
        ),
    }
    document = {
        "level": "level_07",
        "run_id": manifest.get("run_id"),
        "algorithm": manifest.get("algorithm"),
        "status": solver.get("status"),
        "validation_status": manifest.get("validation_status"),
        "runtime_seconds": runtime,
        "used_containers": used,
        "objective_value": objective,
        "balance_lns_termination_reason": solver.get("balance_lns_termination_reason"),
        "balance_outcome_class": outcome_class,
        "gates": gates,
        "accepted": all(gates.values()),
    }
    output = run_dir / "reports" / "level_07_acceptance_assessment.json"
    output.write_text(json.dumps(document, indent=2), encoding="utf-8")
    print(json.dumps(document, indent=2))
    print(f"Assessment: {output}")
    return 0 if document["accepted"] else 2


def _read(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Required Level 7 artifact is missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _used_container_count(path: Path) -> int:
    if not path.is_file():
        raise FileNotFoundError(f"Required Level 7 artifact is missing: {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        return sum(
            str(row.get("used", "")).strip().lower() == "true"
            for row in csv.DictReader(handle)
        )


if __name__ == "__main__":
    raise SystemExit(main())
