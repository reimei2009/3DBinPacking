"""Fail-closed evaluation for MES deadline reliability diagnostic runs."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import pandas as pd

from ..provenance import sha256_file


EXPECTED_CORPORA = {
    "level_04": "level_04_mes_deadline_reliability_v1",
    "level_05": "level_05_mes_deadline_reliability_v1",
}

OFFICIAL_SOURCE_COMMIT = "ad0d23c7d5cc59ddb70bde38a5e75fc12e433e49"
OFFICIAL_ARTIFACT_CHECKSUMS = {
    "level_04": {
        "manifest_sha256": "bdf3f25af56d4dee42bdf50f040dcfee0b41916930178537ab356a2fc1bc4952",
        "results_sha256": "2f23a21146a077bdb066ee9208be44a88680b9bb6957e20124c7c7905b683676",
    },
    "level_05": {
        "manifest_sha256": "1e63495087ef66a895ff53c9ab37db508f184606dda5e1484184b70d55d00931",
        "results_sha256": "3a28cb69621000b36d083c12f5771af5817648d970049c41404f35f6659bc754",
    },
}


def _boolean_series(values: pd.Series) -> pd.Series:
    return values.map(
        lambda value: value is True
        or (isinstance(value, str) and value.strip().lower() == "true")
    )


@dataclass(frozen=True)
class MesDeadlineReliabilityDecision:
    decision: str
    evidence_eligible: bool
    operation_to_harden: str | None
    execution_count: int
    contaminated_execution_count: int
    valid_execution_count: int
    deterministic_group_count: int
    maximum_clean_operation_seconds: float
    maximum_clean_overshoot_seconds: float
    longest_operation: str | None
    artifacts: tuple[dict[str, Any], ...]

    def payload(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "evidence_eligible": self.evidence_eligible,
            "operation_to_harden": self.operation_to_harden,
            "execution_count": self.execution_count,
            "contaminated_execution_count": self.contaminated_execution_count,
            "valid_execution_count": self.valid_execution_count,
            "deterministic_group_count": self.deterministic_group_count,
            "maximum_clean_operation_seconds": self.maximum_clean_operation_seconds,
            "maximum_clean_overshoot_seconds": self.maximum_clean_overshoot_seconds,
            "longest_operation": self.longest_operation,
            "artifacts": list(self.artifacts),
        }


def evaluate_mes_deadline_reliability(
    run_directories: dict[str, str | Path],
    *,
    expected_executions_per_level: int = 9,
    expected_repeats_per_group: int = 3,
    deadline_seconds: float = 180.0,
    operation_threshold_seconds: float = 1.0,
    expected_source_commit: str | None = None,
    expected_checksums: dict[str, dict[str, str]] | None = None,
) -> MesDeadlineReliabilityDecision:
    frames: list[pd.DataFrame] = []
    artifacts: list[dict[str, Any]] = []
    for level, expected_corpus in EXPECTED_CORPORA.items():
        if level not in run_directories:
            raise ValueError(f"Missing diagnostic run for {level}")
        run_dir = Path(run_directories[level]).resolve()
        manifest = run_dir / "manifest.json"
        results = run_dir / "benchmark" / "results.csv"
        if not manifest.is_file() or not results.is_file():
            raise ValueError(f"Incomplete diagnostic artifacts in {run_dir}")
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        if payload.get("corpus_id") != expected_corpus:
            raise ValueError(
                f"Unexpected corpus for {level}: {payload.get('corpus_id')}"
            )
        if payload.get("run_type") != "benchmark_corpus":
            raise ValueError(f"Unexpected run type for {level}: {payload.get('run_type')}")
        if payload.get("status") != "SUCCESS":
            raise ValueError(f"Diagnostic run for {level} is not successful")
        if payload.get("git_dirty") is not False:
            raise ValueError(f"Diagnostic run for {level} must use a clean source tree")
        if expected_source_commit and payload.get("git_commit") != expected_source_commit:
            raise ValueError(
                f"Unexpected source commit for {level}: {payload.get('git_commit')}"
            )
        if payload.get("execution_count") != expected_executions_per_level:
            raise ValueError(f"Manifest execution count mismatch for {level}")
        if payload.get("successful_execution_count") != expected_executions_per_level:
            raise ValueError(f"Manifest success count mismatch for {level}")
        frame = pd.read_csv(results)
        if len(frame) != expected_executions_per_level:
            raise ValueError(
                f"{level} requires {expected_executions_per_level} executions, got {len(frame)}"
            )
        required = {
            "deadline_reliability_enabled",
            "deadline_reliability_classification",
            "deadline_reliability_evidence_eligible",
            "deadline_reliability_deadline_overshoot_seconds",
            "deadline_reliability_max_operation",
            "deadline_reliability_max_operation_active_seconds",
            "case_id",
            "algorithm",
            "random_seed",
            "repeat",
            "status",
            "success",
            "validation_valid",
            "official_objective",
            "placement_signature",
        }
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"{level} diagnostic results miss columns: {sorted(missing)}")
        if not _boolean_series(frame["deadline_reliability_enabled"]).all():
            raise ValueError(f"{level} contains executions without observer telemetry")
        successful = _boolean_series(frame["success"])
        valid = _boolean_series(frame["validation_valid"])
        if not (successful & valid & frame["status"].eq("FEASIBLE")).all():
            raise ValueError(f"{level} contains an execution that is not FEASIBLE + VALID")
        if frame["official_objective"].isna().any() or frame["placement_signature"].isna().any():
            raise ValueError(f"{level} contains incomplete solution evidence")
        group_columns = ["case_id", "algorithm", "random_seed"]
        groups = list(frame.groupby(group_columns, dropna=False, sort=True))
        if len(groups) * expected_repeats_per_group != expected_executions_per_level:
            raise ValueError(f"Unexpected deterministic group count for {level}")
        for key, group in groups:
            if (
                len(group) != expected_repeats_per_group
                or set(group["repeat"].astype(int))
                != set(range(1, expected_repeats_per_group + 1))
            ):
                raise ValueError(f"Incomplete repeat group for {level}: {key}")
            if group["official_objective"].astype(str).nunique(dropna=False) != 1:
                raise ValueError(f"Objective is not deterministic for {level}: {key}")
            if group["placement_signature"].astype(str).nunique(dropna=False) != 1:
                raise ValueError(f"Placement is not deterministic for {level}: {key}")
        manifest_sha256 = sha256_file(manifest)
        results_sha256 = sha256_file(results)
        if expected_checksums is not None:
            if level not in expected_checksums:
                raise ValueError(f"Missing locked checksums for {level}")
            expected = expected_checksums[level]
            if manifest_sha256 != expected.get("manifest_sha256"):
                raise ValueError(f"Manifest checksum mismatch for {level}")
            if results_sha256 != expected.get("results_sha256"):
                raise ValueError(f"Results checksum mismatch for {level}")
        frame = frame.copy()
        frame["diagnostic_level"] = level
        frames.append(frame)
        artifacts.append({
            "level": level,
            "corpus_id": expected_corpus,
            "run_id": payload.get("run_id"),
            "run_directory": f"outputs/{level}/runs/{payload.get('run_id')}",
            "source_commit": payload.get("git_commit"),
            "git_dirty": payload.get("git_dirty"),
            "manifest_sha256": manifest_sha256,
            "results_sha256": results_sha256,
        })
    combined = pd.concat(frames, ignore_index=True)
    eligible = _boolean_series(
        combined["deadline_reliability_evidence_eligible"]
    )
    contaminated = int((~eligible).sum())
    clean = combined[eligible]
    # Active-time excludes Windows suspend, so operation duration remains useful
    # for suspend-classified rows. Host contention and clock discontinuity can
    # inflate it and are deliberately excluded. Overshoot uses only clean rows.
    operation_eligible = eligible | (
        combined["deadline_reliability_classification"]
        == "SYSTEM_SUSPEND_DETECTED"
    )
    operation_rows = combined[operation_eligible]
    max_operation = float(
        pd.to_numeric(
            operation_rows["deadline_reliability_max_operation_active_seconds"],
            errors="coerce",
        ).fillna(0.0).max()
    ) if len(operation_rows) else 0.0
    longest_operation: str | None = None
    if len(operation_rows):
        longest_index = pd.to_numeric(
            operation_rows["deadline_reliability_max_operation_active_seconds"],
            errors="coerce",
        ).fillna(0.0).idxmax()
        value = operation_rows.loc[longest_index, "deadline_reliability_max_operation"]
        longest_operation = None if pd.isna(value) else str(value)
    max_overshoot = float(
        pd.to_numeric(
            clean["deadline_reliability_deadline_overshoot_seconds"], errors="coerce",
        ).fillna(0.0).max()
    ) if len(clean) else 0.0
    overshoot_tolerance = max(1.0, 0.01 * deadline_seconds)
    operation_to_harden: str | None = None
    if max_operation > operation_threshold_seconds or max_overshoot > overshoot_tolerance:
        decision = "TARGETED_HARDENING_REQUIRED"
        if len(operation_rows):
            operation_to_harden = longest_operation
    elif contaminated:
        decision = "NO_COOPERATIVE_HARDENING_REQUIRED_ENVIRONMENTAL_NOISE"
    else:
        decision = "NO_COOPERATIVE_HARDENING_REQUIRED"
    return MesDeadlineReliabilityDecision(
        decision=decision,
        evidence_eligible=contaminated == 0,
        operation_to_harden=operation_to_harden,
        execution_count=len(combined),
        contaminated_execution_count=contaminated,
        valid_execution_count=int(
            (_boolean_series(combined["success"]) & _boolean_series(combined["validation_valid"])).sum()
        ),
        deterministic_group_count=sum(
            frame.groupby(["case_id", "algorithm", "random_seed"], dropna=False).ngroups
            for frame in frames
        ),
        maximum_clean_operation_seconds=max_operation,
        maximum_clean_overshoot_seconds=max_overshoot,
        longest_operation=longest_operation,
        artifacts=tuple(artifacts),
    )
