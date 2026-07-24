"""Typed gate for evaluating, but not registering, the Level 6 runtime candidate."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


_SOLUTION_TABLES = frozenset({
    "nesting_relations.csv", "nesting_height.csv", "nesting_compounds.csv",
    "compound_support.csv", "stacks.csv", "load_bearing.csv", "load_transfer.csv",
})
_VALIDATION_DOCUMENTS = frozenset({
    "nesting_validation.json", "compound_geometry_validation.json",
    "stack_validation.json", "load_bearing_validation.json",
})
_METADATA = frozenset({
    "fixture_adapter", "nesting_construction_policy", "feasibility_policy",
    "compound_validation_status",
})


@dataclass(frozen=True)
class Level06RuntimeCandidateContract:
    algorithm_id: str
    entry_point: str
    construction_policy: str
    feasibility_policy: str
    validator: str
    fixture_id: str
    deterministic_repeats: int


def load_runtime_candidate_contract(config: dict[str, Any]) -> Level06RuntimeCandidateContract:
    """Validate the frozen evaluation gate without creating a runnable level."""
    candidate = config.get("runtime_candidate")
    if not isinstance(candidate, dict):
        raise ValueError("Level 6 runtime candidate config requires runtime_candidate")
    expected = {
        "contract_version": 1,
        "algorithm_id": "extreme_point_ffd_nesting_fixture",
        "entry_point": "container_packing.levels.level_06_ffd_adapter.solve_nesting_aware_ffd_fixture",
        "orientation_mode": "fixed_xyz_only",
        "construction_policy": "explicit_nesting_best_fit_chain_v1",
        "feasibility_policy": "level_06_compound_geometry_payload_exact_support_stackability_load_bearing",
        "validator": "compound_root_effective_envelope_geometry_v1",
    }
    for field, value in expected.items():
        if candidate.get(field) != value:
            raise ValueError(f"Level 6 runtime_candidate.{field} must be {value!r}")
    if candidate.get("status") not in {
        "fixture_accepted_not_registered", "experimental_registered_not_default",
    }:
        raise ValueError("Level 6 runtime candidate has an unsupported promotion status")
    output = candidate.get("output")
    if not isinstance(output, dict) or output.get("run_path") != "outputs/level_06/runs/<run_id>":
        raise ValueError("Level 6 runtime candidate output path must be level-isolated")
    if set(output.get("required_solution_tables", ())) != _SOLUTION_TABLES:
        raise ValueError("Level 6 runtime candidate must declare the complete solution-table contract")
    if set(output.get("required_validation_documents", ())) != _VALIDATION_DOCUMENTS:
        raise ValueError("Level 6 runtime candidate must declare the complete validation-document contract")
    if set(output.get("required_metadata", ())) != _METADATA:
        raise ValueError("Level 6 runtime candidate must declare the required provenance metadata")
    fixture = candidate.get("acceptance_fixture")
    if not isinstance(fixture, dict):
        raise ValueError("Level 6 runtime candidate requires an acceptance_fixture")
    if (
        fixture.get("fixture_id") != "declared_chain_host_child_v1"
        or fixture.get("expected_status") != "FEASIBLE"
        or fixture.get("expected_validation_status") != "VALID"
        or fixture.get("expected_compound_count") != 1
        or fixture.get("expected_relation_count") != 1
        or fixture.get("deterministic_repeats") != 2
    ):
        raise ValueError("Level 6 runtime candidate acceptance fixture is not the frozen baseline")
    gates = candidate.get("promotion_gates")
    if not isinstance(gates, list) or "manual_review_before_registry_cli_or_ui" not in gates:
        raise ValueError("Level 6 runtime candidate must retain the manual promotion gate")
    return Level06RuntimeCandidateContract(
        candidate["algorithm_id"], candidate["entry_point"], candidate["construction_policy"],
        candidate["feasibility_policy"], candidate["validator"], fixture["fixture_id"],
        fixture["deterministic_repeats"],
    )
