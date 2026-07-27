"""Typed promotion gate for the unregistered Level 7 fixture bundle."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


_SOLUTION_TABLES = frozenset({
    "nesting_relations.csv", "nesting_height.csv", "nesting_compounds.csv",
    "compound_support.csv", "stacks.csv", "load_bearing.csv", "load_transfer.csv",
    "center_of_mass.csv",
})
_VALIDATION_DOCUMENTS = frozenset({
    "nesting_validation.json", "compound_geometry_validation.json",
    "stack_validation.json", "load_bearing_validation.json", "balance_validation.json",
})
_METADATA = frozenset({
    "level_07_fixture_validation_only", "center_of_mass_model", "balance_profile",
    "balance_validation_status", "balanced_container_count", "unbalanced_container_count",
})


@dataclass(frozen=True)
class Level07RuntimeCandidateContract:
    algorithm_id: str
    entry_point: str
    fixture_id: str
    deterministic_repeats: int
    output_run_path: str


def load_runtime_candidate_contract(config: dict[str, Any]) -> Level07RuntimeCandidateContract:
    """Validate the frozen, non-executable Level 7 promotion contract."""
    candidate = config.get("runtime_candidate")
    if not isinstance(candidate, dict):
        raise ValueError("Level 7 runtime candidate config requires runtime_candidate")
    expected = {
        "contract_version": 1,
        "status": "fixture_accepted_not_registered",
        "algorithm_id": "level_07_fixture_validation_bundle",
        "entry_point": "container_packing.levels.level_07_fixture_output.write_level_07_fixture_bundle_run",
        "orientation_mode": "fixed_xyz_compound_roots_only",
        "inherited_validator": "level_06_compound_root_bundle_v1",
        "balance_validator": "mass_weighted_item_geometric_center_v1",
    }
    for field, value in expected.items():
        if candidate.get(field) != value:
            raise ValueError(f"Level 7 runtime_candidate.{field} must be {value!r}")
    output = candidate.get("output")
    if not isinstance(output, dict) or output.get("run_path") != "outputs/level_07/runs/<run_id>":
        raise ValueError("Level 7 runtime candidate output path must be level-isolated")
    if set(output.get("required_solution_tables", ())) != _SOLUTION_TABLES:
        raise ValueError("Level 7 runtime candidate must declare the complete solution-table contract")
    if set(output.get("required_validation_documents", ())) != _VALIDATION_DOCUMENTS:
        raise ValueError("Level 7 runtime candidate must declare the complete validation-document contract")
    if set(output.get("required_metadata", ())) != _METADATA:
        raise ValueError("Level 7 runtime candidate must declare the required provenance metadata")
    fixture = candidate.get("acceptance_fixture")
    if not isinstance(fixture, dict) or (
        fixture.get("fixture_id") != "declared_multi_compound_chain_and_top_balance_v1"
        or fixture.get("expected_validation_status") != "VALID"
        or fixture.get("expected_compound_count") != 2
        or fixture.get("expected_relation_count") != 2
        or fixture.get("expected_load_transfer_edge_count") != 1
        or fixture.get("expected_balanced_container_count") != 1
        or fixture.get("deterministic_repeats") != 2
    ):
        raise ValueError("Level 7 runtime candidate acceptance fixture is not the frozen baseline")
    gates = candidate.get("promotion_gates")
    if not isinstance(gates, list) or "manual_review_before_registry_cli_ui_or_solver" not in gates:
        raise ValueError("Level 7 runtime candidate must retain the manual promotion gate")
    return Level07RuntimeCandidateContract(
        candidate["algorithm_id"], candidate["entry_point"], fixture["fixture_id"],
        fixture["deterministic_repeats"], output["run_path"],
    )
