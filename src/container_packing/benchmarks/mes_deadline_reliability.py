"""Fail-closed evaluation for MES deadline reliability diagnostic runs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from ..provenance import sha256_file


EXPECTED_CORPORA = {
    "level_04": "level_04_mes_deadline_reliability_v1",
    "level_05": "level_05_mes_deadline_reliability_v1",
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
    maximum_clean_operation_seconds: float
    maximum_clean_overshoot_seconds: float
    artifacts: tuple[dict[str, Any], ...]

    def payload(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "evidence_eligible": self.evidence_eligible,
            "operation_to_harden": self.operation_to_harden,
            "execution_count": self.execution_count,
            "contaminated_execution_count": self.contaminated_execution_count,
            "maximum_clean_operation_seconds": self.maximum_clean_operation_seconds,
            "maximum_clean_overshoot_seconds": self.maximum_clean_overshoot_seconds,
            "artifacts": list(self.artifacts),
        }


def evaluate_mes_deadline_reliability(
    run_directories: dict[str, str | Path],
    *,
    expected_executions_per_level: int = 9,
    deadline_seconds: float = 180.0,
    operation_threshold_seconds: float = 1.0,
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
        import json

        payload = json.loads(manifest.read_text(encoding="utf-8"))
        if payload.get("corpus_id") != expected_corpus:
            raise ValueError(
                f"Unexpected corpus for {level}: {payload.get('corpus_id')}"
            )
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
        }
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"{level} diagnostic results miss columns: {sorted(missing)}")
        if not _boolean_series(frame["deadline_reliability_enabled"]).all():
            raise ValueError(f"{level} contains executions without observer telemetry")
        frame = frame.copy()
        frame["diagnostic_level"] = level
        frames.append(frame)
        artifacts.append({
            "level": level,
            "run_directory": str(run_dir),
            "manifest_sha256": sha256_file(manifest),
            "results_sha256": sha256_file(results),
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
            index = pd.to_numeric(
                operation_rows["deadline_reliability_max_operation_active_seconds"],
                errors="coerce",
            ).fillna(0.0).idxmax()
            operation = operation_rows.loc[
                index, "deadline_reliability_max_operation"
            ]
            operation_to_harden = None if pd.isna(operation) else str(operation)
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
        maximum_clean_operation_seconds=max_operation,
        maximum_clean_overshoot_seconds=max_overshoot,
        artifacts=tuple(artifacts),
    )
