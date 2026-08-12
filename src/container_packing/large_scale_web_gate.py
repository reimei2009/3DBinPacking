"""Validate manual scale evidence before exposing a large dataset on the web UI."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .dataset_usage import validate_generation_manifest_files


REQUIRED_ITEM_COUNTS = frozenset({1_000, 5_000, 10_000, 12_389})
EXPECTED_SUITE_ID = "level_02_solver_research_i20000_f5000_web_gate_v1"


@dataclass(frozen=True)
class LargeScaleGateResult:
    gate_path: Path
    qualified: bool
    item_counts: tuple[int, ...]
    run_id: str


def qualify_large_scale_web_profile(
    run_dir: Path,
    generation_manifest: Path,
    gate_path: Path,
    *,
    maximum_peak_rss_bytes: int = 8 * 1024**3,
) -> LargeScaleGateResult:
    """Publish the UI gate only for complete, deterministic, bounded evidence."""
    run_dir = run_dir.resolve()
    run_manifest_path = run_dir / "manifest.json"
    results_path = run_dir / "benchmark" / "results.csv"
    if not run_manifest_path.is_file() or not results_path.is_file():
        raise ValueError(f"Benchmark run is missing manifest/results artifacts: {run_dir}")
    run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
    if run_manifest.get("suite_id") != EXPECTED_SUITE_ID:
        raise ValueError(
            f"Expected suite {EXPECTED_SUITE_ID}, got {run_manifest.get('suite_id')!r}"
        )
    dataset = validate_generation_manifest_files(
        generation_manifest, file_keys=("solver_items", "solver_containers"),
    )
    if not dataset.payload.get("solver_acceptance_allowed"):
        raise ValueError("Generated dataset is not qualified for solver execution")
    frame = pd.read_csv(results_path)
    required_columns = {
        "item_count", "status", "success", "validation_valid", "objective_value",
        "placement_signature", "official_objective", "repeat", "peak_rss_bytes",
    }
    missing = sorted(required_columns - set(frame.columns))
    if missing:
        raise ValueError(f"Benchmark results are missing columns: {', '.join(missing)}")
    counts = frozenset(int(value) for value in frame["item_count"].unique())
    if counts != REQUIRED_ITEM_COUNTS:
        raise ValueError(
            f"Scale gate requires item counts {sorted(REQUIRED_ITEM_COUNTS)}, got {sorted(counts)}"
        )
    allowed_timeouts = {"TIME_LIMIT", "REPLAY_TIME_LIMIT"}
    for row in frame.to_dict(orient="records"):
        success = bool(row["success"])
        validation_valid = bool(row["validation_valid"])
        status = str(row["status"])
        objective_present = not pd.isna(row["objective_value"]) or (
            isinstance(row["official_objective"], str) and bool(row["official_objective"].strip())
        )
        if success:
            if not validation_valid or not objective_present:
                raise ValueError("Successful scale-gate rows must be independently VALID with objective")
        elif status not in allowed_timeouts or objective_present:
            raise ValueError(
                f"Scale-gate failure {status!r} is not an explicit objective-free timeout"
            )
        if int(row["peak_rss_bytes"] or 0) > maximum_peak_rss_bytes:
            raise ValueError("Scale-gate peak memory exceeds the configured web guard")
    successful = frame[frame["success"].astype(bool)]
    for _, group in successful.groupby(["item_count", "algorithm", "random_seed"]):
        if group["repeat"].nunique() != 2:
            raise ValueError("Every successful scale case requires two repeats")
        if group["placement_signature"].nunique() != 1 or group["official_objective"].nunique() != 1:
            raise ValueError("Successful scale-gate repeats are not deterministic")
    gate_path = gate_path.resolve()
    gate_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "qualified": True,
        "dataset_profile_id": dataset.payload["profile_id"],
        "generation_manifest_checksum": dataset.manifest_checksum,
        "benchmark_run_id": str(run_manifest.get("run_id", run_dir.name)),
        "suite_id": EXPECTED_SUITE_ID,
        "item_counts": sorted(counts),
        "maximum_peak_rss_bytes": maximum_peak_rss_bytes,
        "accepted_outcomes": ["VALID", "TIME_LIMIT"],
    }
    temporary = gate_path.with_suffix(gate_path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(gate_path)
    return LargeScaleGateResult(
        gate_path=gate_path,
        qualified=True,
        item_counts=tuple(sorted(counts)),
        run_id=payload["benchmark_run_id"],
    )
