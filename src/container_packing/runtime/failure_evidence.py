"""Canonical failure evidence shared by pipelines, benchmarks and UI consumers."""

from __future__ import annotations

from typing import Any, Mapping


TERMINATION_REASON_KEYS = (
    "inventory_search_termination_reason",
    "construction_termination_reason",
    "inventory_construction_termination_reason",
    "container_consolidation_termination_reason",
)


class ExperimentExecutionError(RuntimeError):
    """Carry the last trustworthy experiment metadata across a technical failure."""

    def __init__(
        self,
        *,
        stage: str,
        metadata: Mapping[str, Any],
        cause: Exception,
    ) -> None:
        self.stage = str(stage)
        self.metadata = failure_metadata(
            metadata,
            stage=self.stage,
            error=cause,
            failure_class=(
                "OUTPUT_PUBLICATION_FAILED"
                if self.stage in {"reporting", "post_write"}
                else "EXPERIMENT_EXECUTION_FAILED"
            ),
        )
        self.original_exception = cause
        super().__init__(
            f"{self.stage} failed with {type(cause).__name__}: {cause}"
        )


def canonical_termination_reason(metadata: Mapping[str, Any]) -> str | None:
    """Return the first canonical stop reason without inventing one."""
    for key in TERMINATION_REASON_KEYS:
        value = metadata.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return None


def failure_metadata(
    metadata: Mapping[str, Any] | None,
    *,
    stage: str,
    error: Exception | None = None,
    failure_class: str | None = None,
    requested_item_count: int | None = None,
    requested_container_count: int | None = None,
) -> dict[str, Any]:
    """Build a failure snapshot while nulling every official quality field."""
    result = dict(metadata or {})
    prior_status = result.get("status")
    prior_objective = result.get("objective_value")
    if prior_status is not None:
        result.setdefault("computation_status_before_failure", prior_status)
    if prior_objective is not None:
        result.setdefault("candidate_objective_value", prior_objective)
    result.update({
        "status": "ERROR",
        "failure_stage": str(stage),
        "failure_class": failure_class or "EXPERIMENT_EXECUTION_FAILED",
        "objective_value": None,
        "official_objective": None,
        "official_secondary_search_score": None,
        "diagnostic_secondary_search_score": None,
        "objective_reported": False,
    })
    result.setdefault("requested_item_count", requested_item_count)
    result.setdefault("requested_container_count", requested_container_count)
    reason = canonical_termination_reason(result)
    if reason is not None:
        result["search_termination_reason"] = reason
    if error is not None:
        result["error_type"] = type(error).__name__
        result["error_message"] = str(error)
    return result


def missing_failure_evidence_fields(metadata: Mapping[str, Any]) -> list[str]:
    """Expose incomplete diagnostics without failing output publication."""
    required = ("n_items", "n_containers")
    return [key for key in required if metadata.get(key) is None]
