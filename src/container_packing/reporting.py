"""Level-isolated, reproducible output generation."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from .provenance import runtime_metadata, sha256_file
from .runtime.structured_logging import append_event
from .schemas import Container, Placement, ValidationResult
from .visualization.plotly_3d import write_html_views
from .visualization.scene_schema import build_scene

OUTPUT_SCHEMA_VERSION = "1.0"


def write_text(path: str | Path, value: str) -> None:
    """Atomically replace a small text artifact within its destination folder."""
    target = Path(path)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(target)


def write_placements(path: str | Path, placements: list[Placement]) -> None:
    rows = []
    for placement in placements:
        row = asdict(placement)
        row["volume_m3"] = placement.volume_m3
        rows.append(row)
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8")


def container_summary(placements: list[Placement], containers: list[Container]) -> pd.DataFrame:
    rows = []
    for container in containers:
        group = [value for value in placements if value.container_id == container.container_id]
        weight = sum(value.weight_kg for value in group)
        volume = sum(value.volume_m3 for value in group)
        rows.append({
            "container_id": container.container_id, "used": bool(group), "item_count": len(group),
            "loaded_weight_kg": weight, "max_weight_kg": container.max_weight_kg,
            "weight_utilization_pct": 100 * weight / container.max_weight_kg,
            "loaded_volume_m3": volume, "container_volume_m3": container.volume_m3,
            "volume_utilization_pct": 100 * volume / container.volume_m3, "cost": container.cost,
        })
    return pd.DataFrame(rows)


def write_json(path: str | Path, data: dict[str, Any]) -> None:
    write_text(path, json.dumps(data, indent=2, ensure_ascii=False, default=str))


def validation_payload(result: ValidationResult) -> dict[str, Any]:
    return {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "valid": result.valid,
        "issue_count": len(result.issues),
        "issues": [asdict(issue) for issue in result.issues],
    }


def solver_payload(metadata: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "status", "solver", "solver_message", "algorithm_runtime_seconds", "objective_value",
        "n_items", "n_containers", "n_pairs", "n_variables", "n_constraints",
        "constraint_nnz", "big_m", "objective_priority_constant",
        "algorithm_kind", "algorithm_role", "failure_interpretation", "optimality_proven",
        "item_ordering", "point_ordering",
        "mip_gap", "mip_dual_bound", "mip_node_count",
        "feasibility_policy", "candidate_feasibility_checks", "geometry_rejected_candidates",
        "strict_lifo_candidate_feasibility_enabled", "strict_lifo_candidates_evaluated",
        "strict_lifo_rejected_candidates", "strict_lifo_valid_candidates",
        "strict_lifo_rejection_examples",
        "delivery_dependency_candidates_evaluated",
        "delivery_dependency_rejected_candidates",
        "delivery_dependency_valid_candidates",
        "delivery_dependency_rejection_examples",
        "sequential_balance_construction_enabled",
        "sequential_balance_construction_mode",
        "sequential_balance_candidates_evaluated",
        "sequential_balance_rejected_candidates",
        "sequential_balance_valid_candidates",
        "delivery_balance_scoring_enabled",
        "delivery_final_candidate_selection",
        "delivery_final_candidates_evaluated",
        "delivery_final_candidate_valid",
        "delivery_final_candidate_records",
        "orientation_provider", "orientation_profile", "orientation_candidates_evaluated",
        "heuristic_support_threshold", "heuristic_support_epsilon_mm",
        "support_rejected_candidates", "support_valid_candidates",
        "container_selection_strategy", "candidate_scoring", "subset_enumeration_limit",
        "candidate_subsets_evaluated", "packing_attempts", "extreme_points_evaluated",
        "construction_complete", "construction_termination_reason",
        "construction_failed_item_id", "best_partial_placement_count",
        "unpacked_item_count", "unpacked_items", "construction_attempt_signature",
        "container_subset_policy", "container_subset_search_mode",
        "container_subset_exhaustive_max_containers",
        "container_subset_max_candidates_per_count",
        "container_subset_candidates_generated",
        "container_subset_capacity_pruned",
        "container_subset_compatibility_pruned",
        "container_subset_deadline_reached",
        "container_subset_soft_volume_buffer_ratio",
        "container_subset_cardinalities_considered",
        "container_subset_payload_lower_bound",
        "container_subset_volume_lower_bound",
        "container_subset_aggregate_lower_bound",
        "container_subset_attempts",
        "container_search_enabled",
        "container_search_time_limit_seconds",
        "container_inventory_count",
        "requested_used_container_count",
        "hard_precheck_valid",
        "hard_precheck_issue_count",
        "hard_precheck_issues",
        "inventory_physical_container_count",
        "inventory_equivalent_type_count",
        "inventory_unavailable_container_count",
        "inventory_container_types",
        "initial_used_container_count",
        "max_used_container_count",
        "automatically_increase_container_count",
        "candidate_container_ids",
        "space_representation", "empty_spaces_evaluated", "empty_spaces_generated",
        "empty_spaces_pruned", "maximum_active_spaces",
        "initial_algorithm", "initial_constructor", "repair_constructor", "neighborhoods", "acceptance", "max_iterations", "max_neighbors",
          "subset_candidate_limit", "hill_climbing_iterations", "neighbors_evaluated",
          "feasible_neighbors", "rejected_neighbors", "repacking_attempts", "accepted_operators", "initial_score", "final_score", "improved",
          "neighbors_per_iteration", "initial_temperature", "cooling_rate", "minimum_temperature",
          "final_temperature", "annealing_iterations", "accepted_moves", "accepted_worse_moves",
          "best_improvements", "accepted_operator_counts", "final_current_score", "best_score",
        "allow_worse_subsets",
          "support_grid_x", "support_grid_y", "support_grid_size", "support_threshold",
          "minimum_supported_points", "floor_variable_count", "support_point_variable_count",
          "center_support_variable_count",
          "capacity_strengthening_enabled", "capacity_strengthening_cut_count",
          "container_count_lower_bound", "volume_container_count_lower_bound",
          "payload_container_count_lower_bound",
          "model_support_audit_valid", "model_support_audit_issue_count", "model_support_audit_examples",
          "stackability_rejected_candidates", "stackability_valid_candidates",
          "stackability_parent_selection", "stackability_max_layers_semantics",
          "load_bearing_rejected_candidates", "load_bearing_valid_candidates",
          "load_bearing_capacity_profile", "load_transfer_model",
          "nesting_contract_version", "nesting_validation_model", "nesting_relation_count",
          "compound_geometry_model", "compound_count",
          "fixture_adapter", "nesting_construction_policy",
          "nesting_eligible_child_count", "nesting_candidate_relation_count",
          "nesting_accepted_relation_count", "nesting_rejected_candidate_count",
          "compound_candidate_count", "compound_validation_status",
          "compound_relation_graph_mode", "compound_search_item_count",
          "center_of_mass_model", "balance_profile", "balance_validation_status",
          "balanced_container_count", "unbalanced_container_count",
          "balance_pipeline", "balance_repair_phase", "balance_repair_attempts",
          "balance_repair_opened_extra_containers",
          "balance_repair_candidates_evaluated",
          "balance_repair_improving_candidates_validated",
          "balance_repair_relocation_candidates", "balance_repair_swap_candidates",
          "balance_repair_partial_repack_candidates",
          "balance_repair_accepted_moves", "balance_repair_termination_reason",
          "balance_repair_initial_max_violation", "balance_repair_final_max_violation",
          "balance_violation_baseline_max", "balance_violation_after_local_max",
          "balance_violation_after_lns_max", "balance_violation_after_rescue_max",
          "balance_repair_initial_container_count", "balance_repair_final_container_count",
          "balance_repair_fixed_phase_seconds", "balance_repair_extra_phase_seconds",
          "balance_repair_time_limit_seconds", "balance_repair_fixed_subset_seconds",
          "balance_repair_extra_container_seconds", "balance_repair_max_candidates",
          "balance_repair_contributor_limit", "balance_repair_max_extra_containers",
          "balance_repair_lns_seconds", "balance_repair_lns_max_candidates",
          "balance_lns_rounds_attempted", "balance_lns_candidates_evaluated",
          "balance_lns_neighborhoods_attempted", "balance_lns_accepted_round",
          "balance_lns_affected_container_ids", "balance_lns_destroyed_item_ids",
          "balance_lns_runtime_seconds", "balance_lns_termination_reason",
        "balance_lns_donor_selection",
        "balance_lns_neighborhood_selection",
        "balance_lns_neighborhood_sizes_attempted",
        "balance_lns_duplicate_candidates_skipped",
        "balance_lns_initial_max_violation", "balance_lns_final_max_violation",
        "balance_rescue_attempted", "balance_rescue_candidates_evaluated",
        "balance_rescue_improving_candidates_validated",
        "balance_rescue_accepted_moves", "balance_rescue_runtime_seconds",
        "balance_rescue_termination_reason",
        "balance_rescue_initial_max_violation",
        "balance_rescue_final_max_violation",
          "balance_execution_mode", "balance_failure_reason",
          "balance_outcome_class", "balance_pipeline_time_limit_seconds",
          "balance_consolidation_attempted", "balance_consolidation_result",
          "balance_consolidation_candidates_evaluated",
          "balance_baseline_runtime_seconds",
          "balance_repair_runtime_seconds", "balance_pipeline_runtime_seconds",
          "candidate_objective_value",
          "unloading_model", "door_face", "delivery_priority_direction", "rehandle_count_mode",
          "total_direct_rehandles", "lifo_compliant_item_count", "lifo_noncompliant_item_count",
          "delivery_stop_count", "delivery_priority_min", "delivery_priority_max",
          "delivery_priority_distribution", "delivery_stop_distribution",
          "delivery_construction_mode_requested", "delivery_construction_mode_selected",
          "delivery_construction_candidates", "delivery_construction_compare_skipped_for_scale",
          "delivery_pipeline_time_limit_seconds", "delivery_baseline_runtime_seconds",
          "delivery_repair_phase", "delivery_repair_candidates_evaluated",
          "delivery_repair_improving_candidates_validated",
          "delivery_repair_relocation_candidates", "delivery_repair_transfer_candidates",
          "delivery_repair_swap_candidates", "delivery_repair_partial_repack_candidates",
          "delivery_container_elimination_enabled",
          "delivery_container_elimination_attempted",
          "delivery_container_elimination_initial_count",
          "delivery_container_elimination_final_count",
          "delivery_container_elimination_attempts",
          "delivery_container_elimination_successes",
          "delivery_container_elimination_candidates_evaluated",
          "delivery_container_elimination_lns_enabled",
          "delivery_container_elimination_lns_attempts",
          "delivery_container_elimination_lns_neighborhoods",
          "delivery_container_elimination_lns_candidates_evaluated",
          "delivery_container_elimination_lns_selected_neighborhood_size",
          "delivery_container_elimination_lns_termination_reason",
          "delivery_stop_assignment_enabled",
          "delivery_stop_assignment_skip_reason",
          "delivery_stop_assignment_beam_width",
          "delivery_stop_assignment_max_plans_per_subset",
          "delivery_stop_assignment_utilization_target",
          "delivery_stop_assignment_time_limit_seconds",
          "delivery_stop_assignment_candidate",
          "delivery_stop_assignment_runtime_seconds",
          "assignment_failure_stage",
          "container_assignment_planner",
          "container_assignment_beam_width",
          "container_assignment_max_plans_per_subset",
          "container_assignment_utilization_target",
          "container_assignment_subsets_evaluated",
          "container_assignment_states_generated",
          "container_assignment_states_capacity_pruned",
          "container_assignment_states_fit_pruned",
          "container_assignment_plans_generated",
          "container_assignment_plans_evaluated",
          "container_assignment_deadline_reached",
          "container_assignment_termination_reason",
          "container_assignment_mode",
          "container_assignment_subset_ids",
          "container_assignment_group_count",
          "container_assignment_planned_used_count",
          "container_assignment_planned_stop_fragmentation",
          "container_assignment_actual_used_count",
          "container_assignment_actual_stop_fragmentation",
          "container_preference_policy",
          "container_affinity_candidates_ranked",
          "container_affinity_preferred_hits",
          "container_affinity_fallback_count",
          "container_affinity_groups_moved_from_first_preference",
          "container_assignment_total_cost",
          "container_assignment_maximum_utilization",
          "container_assignment_utilization_imbalance",
          "container_assignment_signature",
          "delivery_container_elimination_closed_ids",
          "delivery_container_elimination_runtime_seconds",
          "delivery_container_elimination_termination_reason",
          "delivery_repair_neighborhood_candidates", "delivery_repair_neighborhood_attempts",
          "delivery_repair_accepted_moves",
          "delivery_repair_initial_direct_rehandles", "delivery_repair_final_direct_rehandles",
          "delivery_repair_initial_lifo_violations", "delivery_repair_final_lifo_violations",
          "delivery_repair_termination_reason", "delivery_repair_runtime_seconds",
          "delivery_repair_fixed_phase_seconds", "delivery_repair_extra_phase_seconds",
          "delivery_repair_time_limit_seconds", "delivery_repair_fixed_subset_seconds",
          "delivery_repair_extra_container_seconds", "delivery_repair_max_candidates",
          "delivery_repair_contributor_limit", "delivery_repair_max_extra_containers",
          "delivery_repair_relocation_transfer_max_candidates",
          "delivery_repair_swap_max_candidates", "delivery_repair_neighborhood_max_candidates",
          "delivery_repair_neighborhood_sizes", "delivery_repair_operator_time_fractions",
          "delivery_repair_extra_max_candidates",
          "delivery_repair_initial_container_count", "delivery_repair_final_container_count",
          "delivery_outcome_class",
          "sequential_simulation_enabled", "sequential_simulation_status",
          "sequential_simulation_skip_reason", "sequential_simulation_time_limit_seconds",
          "sequential_replay_total_runtime_seconds", "sequential_replay_graph_runtime_seconds",
          "sequential_replay_state_runtime_seconds", "sequential_replay_states_checked",
          "sequential_replay_termination_reason", "sequential_state_validation_mode",
          "sequential_replay_validation_issue_count", "sequential_replay_validation_issue_codes",
          "sequential_replay_first_failed_sequence", "sequential_replay_first_failed_item_id",
          "sequential_replay_first_issue_code", "sequential_replay_first_issue_message",
          "sequential_unloading_order_mode",
          "sequential_balance_order_hard_cog_gate",
          "sequential_balance_order_candidates_evaluated",
          "sequential_balance_order_backtracks",
          "sequential_balance_order_failed_states",
          "sequential_balance_order_priority",
          "sequential_balance_order_ready_item_ids",
          "sequential_balance_order_blocked_item_ids",
          "sequential_balance_order_best_candidate_item_id",
          "sequential_balance_order_best_longitudinal_offset_ratio",
          "sequential_balance_order_best_lateral_offset_ratio",
          "algorithm_parameters",
      )
    return {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        **{key: metadata[key] for key in keys if metadata.get(key) is not None},
    }


def metrics_payload(metadata: dict[str, Any], validation_valid: bool | None) -> dict[str, Any]:
    return {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "level": metadata["level_id"],
        "algorithm": metadata["algorithm_id"],
        "algorithm_role": metadata.get("algorithm_role"),
        "status": metadata["status"],
        "objective_value": metadata.get("objective_value"),
        "candidate_objective_value": metadata.get("candidate_objective_value"),
        "objective_reported": metadata.get("objective_reported", True),
        "container_count": metadata.get("container_count"),
        "total_container_cost": metadata.get("total_container_cost"),
        "n_items": metadata["n_items"],
        "n_containers_available": metadata["n_containers"],
        "algorithm_runtime_seconds": metadata.get("algorithm_runtime_seconds"),
        "mip_gap": metadata.get("mip_gap"),
        "mip_dual_bound": metadata.get("mip_dual_bound"),
        "mip_node_count": metadata.get("mip_node_count"),
        "feasibility_policy": metadata.get("feasibility_policy"),
        "strict_lifo_candidate_feasibility_enabled": metadata.get("strict_lifo_candidate_feasibility_enabled"),
        "strict_lifo_candidates_evaluated": metadata.get("strict_lifo_candidates_evaluated"),
        "strict_lifo_rejected_candidates": metadata.get("strict_lifo_rejected_candidates"),
        "strict_lifo_valid_candidates": metadata.get("strict_lifo_valid_candidates"),
        "sequential_balance_construction_enabled": metadata.get("sequential_balance_construction_enabled"),
        "sequential_balance_construction_mode": metadata.get("sequential_balance_construction_mode"),
        "sequential_balance_candidates_evaluated": metadata.get("sequential_balance_candidates_evaluated"),
        "sequential_balance_rejected_candidates": metadata.get("sequential_balance_rejected_candidates"),
        "sequential_balance_valid_candidates": metadata.get("sequential_balance_valid_candidates"),
        "support_rejected_candidates": metadata.get("support_rejected_candidates"),
        "support_valid_candidates": metadata.get("support_valid_candidates"),
        "validation_valid": validation_valid,
        "item_selection_strategy": metadata.get("item_selection_strategy"),
        "item_selection_seed": metadata.get("item_selection_seed"),
        "selected_item_ids_checksum": metadata.get("selected_item_ids_checksum"),
        "data_profile_kind": metadata.get("data_profile_kind"),
        "dataset_id": metadata.get("dataset_id"),
        "container_catalog_id": metadata.get("container_catalog_id"),
        "comparison_group_id": metadata.get("comparison_group_id"),
        "support_enabled": metadata.get("support_enabled", False),
        "support_threshold": metadata.get("support_threshold"),
        "minimum_exact_support_ratio": metadata.get("minimum_exact_support_ratio"),
        "all_centers_supported": metadata.get("all_centers_supported"),
        "orientation_profile": metadata.get("orientation_profile"),
        "stackability_enabled": metadata.get("stackability_enabled", False),
        "stackability_contract_version": metadata.get("stackability_contract_version"),
        "stackability_data_status": metadata.get("stackability_data_status"),
        "stack_count": metadata.get("stack_count"),
        "maximum_stack_depth": metadata.get("maximum_stack_depth"),
        "load_bearing_enabled": metadata.get("load_bearing_enabled", False),
        "load_transfer_enabled": metadata.get("load_transfer_enabled", False),
        "load_bearing_contract_version": metadata.get("load_bearing_contract_version"),
        "load_bearing_data_status": metadata.get("load_bearing_data_status"),
        "load_bearing_capacity_profile": metadata.get("load_bearing_capacity_profile"),
        "maximum_load_utilization_ratio": metadata.get("maximum_load_utilization_ratio"),
        "minimum_load_safety_margin_kg": metadata.get("minimum_load_safety_margin_kg"),
        "overloaded_item_count": metadata.get("overloaded_item_count"),
        "fragile_item_count": metadata.get("fragile_item_count"),
        "load_transfer_edge_count": metadata.get("load_transfer_edge_count"),
        "nesting_runtime_enabled": metadata.get("nesting_runtime_enabled", False),
        "nesting_relation_count": metadata.get("nesting_relation_count"),
        "maximum_nesting_depth": metadata.get("maximum_nesting_depth"),
        "compound_geometry_model": metadata.get("compound_geometry_model"),
        "compound_count": metadata.get("compound_count"),
        "nesting_construction_policy": metadata.get("nesting_construction_policy"),
        "nesting_accepted_relation_count": metadata.get("nesting_accepted_relation_count"),
        "compound_validation_status": metadata.get("compound_validation_status"),
        "compound_relation_graph_mode": metadata.get("compound_relation_graph_mode"),
        "compound_search_item_count": metadata.get("compound_search_item_count"),
        "center_of_mass_model": metadata.get("center_of_mass_model"),
        "balance_profile": metadata.get("balance_profile"),
        "balance_validation_status": metadata.get("balance_validation_status"),
        "balanced_container_count": metadata.get("balanced_container_count"),
        "unbalanced_container_count": metadata.get("unbalanced_container_count"),
        "unloading_model": metadata.get("unloading_model"),
        "door_face": metadata.get("door_face"),
        "delivery_priority_direction": metadata.get("delivery_priority_direction"),
        "rehandle_count_mode": metadata.get("rehandle_count_mode"),
        "total_direct_rehandles": metadata.get("total_direct_rehandles"),
        "lifo_compliant_item_count": metadata.get("lifo_compliant_item_count"),
        "lifo_noncompliant_item_count": metadata.get("lifo_noncompliant_item_count"),
        "sequential_simulation_enabled": metadata.get("sequential_simulation_enabled"),
        "sequential_simulation_status": metadata.get("sequential_simulation_status"),
        "sequential_simulation_skip_reason": metadata.get("sequential_simulation_skip_reason"),
        "sequential_simulation_time_limit_seconds": metadata.get("sequential_simulation_time_limit_seconds"),
        "sequential_replay_total_runtime_seconds": metadata.get("sequential_replay_total_runtime_seconds"),
        "sequential_replay_graph_runtime_seconds": metadata.get("sequential_replay_graph_runtime_seconds"),
        "sequential_replay_state_runtime_seconds": metadata.get("sequential_replay_state_runtime_seconds"),
        "sequential_replay_states_checked": metadata.get("sequential_replay_states_checked"),
        "sequential_replay_termination_reason": metadata.get("sequential_replay_termination_reason"),
        "sequential_state_validation_mode": metadata.get("sequential_state_validation_mode"),
        "sequential_replay_validation_issue_count": metadata.get("sequential_replay_validation_issue_count"),
        "sequential_replay_validation_issue_codes": metadata.get("sequential_replay_validation_issue_codes"),
        "sequential_replay_first_failed_sequence": metadata.get("sequential_replay_first_failed_sequence"),
        "sequential_replay_first_failed_item_id": metadata.get("sequential_replay_first_failed_item_id"),
        "sequential_replay_first_issue_code": metadata.get("sequential_replay_first_issue_code"),
        "sequential_replay_first_issue_message": metadata.get("sequential_replay_first_issue_message"),
        "sequential_unloading_order_mode": metadata.get("sequential_unloading_order_mode"),
        "sequential_balance_order_hard_cog_gate": metadata.get("sequential_balance_order_hard_cog_gate"),
        "sequential_balance_order_candidates_evaluated": metadata.get("sequential_balance_order_candidates_evaluated"),
        "sequential_balance_order_backtracks": metadata.get("sequential_balance_order_backtracks"),
        "sequential_balance_order_failed_states": metadata.get("sequential_balance_order_failed_states"),
        "sequential_balance_order_priority": metadata.get("sequential_balance_order_priority"),
        "sequential_balance_order_ready_item_ids": metadata.get("sequential_balance_order_ready_item_ids"),
        "sequential_balance_order_blocked_item_ids": metadata.get("sequential_balance_order_blocked_item_ids"),
        "sequential_balance_order_best_candidate_item_id": metadata.get("sequential_balance_order_best_candidate_item_id"),
        "sequential_balance_order_best_longitudinal_offset_ratio": metadata.get("sequential_balance_order_best_longitudinal_offset_ratio"),
        "sequential_balance_order_best_lateral_offset_ratio": metadata.get("sequential_balance_order_best_lateral_offset_ratio"),
    }


def _initialize_run(
    run_dir: Path, metadata: dict[str, Any], config: dict[str, Any],
    items_path: Path, containers_path: Path, project_root: Path,
) -> dict[str, Any]:
    directories = ["input_snapshot", "logs", "solver", "solution", "validation", "metrics", "reports", "visualization"]
    for name in directories:
        (run_dir / name).mkdir(parents=True, exist_ok=True)
    shutil.copy2(items_path, run_dir / "input_snapshot" / "items.csv")
    shutil.copy2(containers_path, run_dir / "input_snapshot" / "containers.csv")
    resolved_config_path = run_dir / "resolved_config.yaml"
    write_text(resolved_config_path, yaml.safe_dump(config, sort_keys=False))
    manifest = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "project": "3d-container-packing",
        "level": metadata["level_id"], "run_id": metadata["run_id"],
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "algorithm": metadata["algorithm_id"], "solver": metadata["solver"],
        "algorithm_role": metadata.get("algorithm_role"),
        "environment": metadata["environment"], "dataset_name": metadata["instance_id"],
        "dataset_files": ["input_snapshot/items.csv", "input_snapshot/containers.csv"],
        "dataset_checksums": {
            "items": sha256_file(items_path), "containers": sha256_file(containers_path),
        },
        "item_selection": {
            "strategy": metadata.get("item_selection_strategy"),
            "seed": metadata.get("item_selection_seed"),
            "selected_item_ids_checksum": metadata.get("selected_item_ids_checksum"),
            "profile": metadata.get("item_profile"),
        },
        "source_adapter": metadata.get("source_adapter"),
        "data_identity": metadata.get("data_identity", {}),
        "dataset_usage": metadata.get("dataset_usage"),
        "container_search": {
            "enabled": metadata.get("container_search_enabled", False),
            "catalog_row_count": metadata.get("container_inventory_count"),
            "available_physical_count": metadata.get(
                "inventory_physical_container_count"
            ),
            "equivalent_type_count": metadata.get(
                "inventory_equivalent_type_count"
            ),
            "requested_initial_used_count": metadata.get(
                "requested_used_container_count"
            ),
            "configured_initial_used_count": metadata.get(
                "initial_used_container_count"
            ),
            "configured_max_used_count": metadata.get(
                "max_used_container_count"
            ),
            "automatically_increase": metadata.get(
                "automatically_increase_container_count"
            ),
        },
        "config_file": metadata.get("config_file"),
        "resolved_config_checksum": sha256_file(resolved_config_path),
        "config_overrides": metadata.get("config_overrides", {}),
        "support_threshold": metadata.get("support_threshold"),
        "orientation_profile": metadata.get("orientation_profile"),
        "orientation_data_status": metadata.get("orientation_data_status"),
        "stackability_contract_version": metadata.get("stackability_contract_version"),
        "stackability_data_status": metadata.get("stackability_data_status"),
        "load_bearing_contract_version": metadata.get("load_bearing_contract_version"),
        "load_bearing_data_status": metadata.get("load_bearing_data_status"),
        "load_bearing_capacity_profile": metadata.get("load_bearing_capacity_profile"),
        "load_transfer_model": metadata.get("load_transfer_model"),
        "nesting_contract_version": metadata.get("nesting_contract_version"),
        "nesting_data_status": metadata.get("nesting_data_status"),
        "nesting_validation_model": metadata.get("nesting_validation_model"),
        "compound_geometry_model": metadata.get("compound_geometry_model"),
        "compound_count": metadata.get("compound_count"),
        "fixture_adapter": metadata.get("fixture_adapter"),
        "nesting_construction_policy": metadata.get("nesting_construction_policy"),
        "compound_relation_graph_mode": metadata.get("compound_relation_graph_mode"),
        "compound_search_item_count": metadata.get("compound_search_item_count"),
        "center_of_mass_model": metadata.get("center_of_mass_model"),
        "balance_profile": metadata.get("balance_profile"),
        "balance_validation_status": metadata.get("balance_validation_status"),
        "balanced_container_count": metadata.get("balanced_container_count"),
        "unbalanced_container_count": metadata.get("unbalanced_container_count"),
        "unloading_model": metadata.get("unloading_model"),
        "door_face": metadata.get("door_face"),
        "delivery_priority_direction": metadata.get("delivery_priority_direction"),
        "rehandle_count_mode": metadata.get("rehandle_count_mode"),
        "total_direct_rehandles": metadata.get("total_direct_rehandles"),
        "lifo_compliant_item_count": metadata.get("lifo_compliant_item_count"),
        "lifo_noncompliant_item_count": metadata.get("lifo_noncompliant_item_count"),
        "sequential_simulation_enabled": metadata.get("sequential_simulation_enabled"),
        "sequential_simulation_status": metadata.get("sequential_simulation_status"),
        "sequential_simulation_skip_reason": metadata.get("sequential_simulation_skip_reason"),
        "sequential_simulation_time_limit_seconds": metadata.get("sequential_simulation_time_limit_seconds"),
        "sequential_replay_total_runtime_seconds": metadata.get("sequential_replay_total_runtime_seconds"),
        "sequential_replay_graph_runtime_seconds": metadata.get("sequential_replay_graph_runtime_seconds"),
        "sequential_replay_state_runtime_seconds": metadata.get("sequential_replay_state_runtime_seconds"),
        "sequential_replay_states_checked": metadata.get("sequential_replay_states_checked"),
        "sequential_replay_termination_reason": metadata.get("sequential_replay_termination_reason"),
        "sequential_unloading_order_mode": metadata.get("sequential_unloading_order_mode"),
        "sequential_balance_order_hard_cog_gate": metadata.get("sequential_balance_order_hard_cog_gate"),
        "sequential_balance_order_candidates_evaluated": metadata.get("sequential_balance_order_candidates_evaluated"),
        "sequential_balance_order_backtracks": metadata.get("sequential_balance_order_backtracks"),
        "sequential_balance_order_failed_states": metadata.get("sequential_balance_order_failed_states"),
        "random_seed": metadata["random_seed"],
        "time_limit_seconds": metadata.get("time_limit_seconds"),
        "active_constraints": metadata.get("active_constraints", [
            "exact_assignment", "container_activation", "boundaries", "payload", "pairwise_non_overlap",
        ]),
        "inactive_constraints": metadata.get("inactive_constraints", [
            "rotation", "stackability", "support", "stability", "fragility", "center_of_gravity",
        ]),
        "status": metadata["status"],
        "validation_status": "NOT_RUN",
        "artifacts": {
            "canonical": [
                "manifest.json", "resolved_config.yaml", "input_snapshot/items.csv",
                "input_snapshot/containers.csv",
            ],
            "exports": ["metrics/metrics.json"],
            "derived": [],
            "diagnostics": ["logs/run.log", "solver/solver_summary.json", "solver/raw_solver_output.txt"],
        },
        **runtime_metadata(project_root),
    }
    write_json(run_dir / "manifest.json", manifest)
    return manifest


def write_status_outputs(
    run_dir: Path, metadata: dict[str, Any], config: dict[str, Any], *,
    items_path: Path, containers_path: Path, project_root: Path,
    validation: ValidationResult | None = None,
    extra_solution_tables: dict[str, list[dict[str, Any]]] | None = None,
    extra_validation_documents: dict[str, dict[str, Any]] | None = None,
) -> None:
    manifest = _initialize_run(run_dir, metadata, config, items_path, containers_path, project_root)
    write_json(run_dir / "solver" / "solver_summary.json", solver_payload(metadata))
    write_text(run_dir / "solver" / "raw_solver_output.txt", metadata.get("solver_message", "") + "\n")
    write_json(run_dir / "metrics" / "metrics.json", metrics_payload(metadata, None if validation is None else validation.valid))
    validation_status = "NOT_RUN"
    if validation is not None:
        validation_status = "VALID" if validation.valid else "INVALID"
        write_json(run_dir / "validation" / "validation_report.json", validation_payload(validation))
        pd.DataFrame(
            [asdict(value) for value in validation.issues],
            columns=["code", "message", "item_ids", "container_id"],
        ).to_csv(run_dir / "validation" / "violations.csv", index=False)
        manifest["validation_status"] = validation_status
        manifest["artifacts"]["canonical"].append("validation/validation_report.json")
        manifest["artifacts"]["exports"].append("validation/violations.csv")
    _write_extra_artifacts(run_dir, manifest, extra_solution_tables, extra_validation_documents)
    append_event(
        run_dir / "logs" / "run.log", "experiment_completed",
        run_id=metadata["run_id"], level=metadata["level_id"], algorithm=metadata["algorithm_id"],
        status=metadata["status"], validation_status=validation_status,
    )
    write_json(run_dir / "manifest.json", manifest)


def write_run_outputs(
    run_dir: Path, placements: list[Placement], containers: list[Container],
    metadata: dict[str, Any], validation: ValidationResult, config: dict[str, Any], *,
    items_path: Path, containers_path: Path, project_root: Path,
    extra_solution_tables: dict[str, list[dict[str, Any]]] | None = None,
    extra_validation_documents: dict[str, dict[str, Any]] | None = None,
    solution_payload_extra: dict[str, Any] | None = None,
    scene_item_metadata: dict[str, dict[str, Any]] | None = None,
    extra_report_lines: list[str] | None = None,
) -> None:
    manifest = _initialize_run(run_dir, metadata, config, items_path, containers_path, project_root)
    manifest["artifacts"]["canonical"].extend(["solution/solution.json", "validation/validation_report.json"])
    manifest["artifacts"]["exports"].extend([
        "solution/placements.csv", "solution/containers.csv", "validation/violations.csv",
    ])
    manifest["artifacts"]["derived"].extend([
        "reports/summary.md", "visualization/scene.json", "visualization/combined_scene.html",
    ])
    summary = container_summary(placements, containers)
    validation_data = validation_payload(validation)
    write_placements(run_dir / "solution" / "placements.csv", placements)
    summary.to_csv(run_dir / "solution" / "containers.csv", index=False)
    write_json(run_dir / "solution" / "solution.json", {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "level": metadata["level_id"],
        "placements": [asdict(value) for value in placements],
        **(solution_payload_extra or {}),
    })
    write_json(run_dir / "solver" / "solver_summary.json", solver_payload(metadata))
    write_text(run_dir / "solver" / "raw_solver_output.txt", metadata.get("solver_message", "") + "\n")
    write_json(run_dir / "validation" / "validation_report.json", validation_data)
    pd.DataFrame([asdict(value) for value in validation.issues], columns=["code", "message", "item_ids", "container_id"]).to_csv(
        run_dir / "validation" / "violations.csv", index=False
    )
    write_json(run_dir / "metrics" / "metrics.json", metrics_payload(metadata, validation.valid))
    _write_extra_artifacts(run_dir, manifest, extra_solution_tables, extra_validation_documents)
    scene = build_scene(
        placements,
        containers,
        level_id=metadata["level_id"],
        algorithm_id=metadata["algorithm_id"],
        validation_status="VALID" if validation.valid else "INVALID",
        item_metadata=scene_item_metadata,
    )
    write_json(run_dir / "visualization" / "scene.json", scene)
    html_views = write_html_views(scene, run_dir / "visualization")
    manifest["artifacts"]["derived"].extend(
        path.relative_to(run_dir).as_posix() for path in html_views[1:]
    )
    append_event(
        run_dir / "logs" / "run.log", "experiment_completed",
        run_id=metadata["run_id"], level=metadata["level_id"], algorithm=metadata["algorithm_id"],
        status=metadata["status"], objective_value=metadata.get("objective_value"),
        validation_status="VALID" if validation.valid else "INVALID",
    )
    write_text(run_dir / "reports" / "summary.md",
        f"# Run {metadata['run_id']}\n\n- Status: {metadata['status']}\n- Objective: {metadata.get('objective_value')}\n"
        f"- Algorithm role: {metadata.get('algorithm_role')}\n"
        f"- Selected containers: {metadata.get('selected_containers', [])}\n- Validation: {validation.valid}\n"
        + ("\n".join(extra_report_lines or []) + "\n" if extra_report_lines else "")
    )
    manifest["validation_status"] = "VALID" if validation.valid else "INVALID"
    write_json(run_dir / "manifest.json", manifest)


def _write_extra_artifacts(
    run_dir: Path,
    manifest: dict[str, Any],
    solution_tables: dict[str, list[dict[str, Any]]] | None,
    validation_documents: dict[str, dict[str, Any]] | None,
) -> None:
    """Persist level-specific artifacts without changing canonical placement schemas."""
    for filename, rows in (solution_tables or {}).items():
        if Path(filename).name != filename or not filename.endswith(".csv"):
            raise ValueError(f"Invalid additional solution filename: {filename}")
        pd.DataFrame(rows).to_csv(run_dir / "solution" / filename, index=False, encoding="utf-8")
        manifest["artifacts"]["exports"].append(f"solution/{filename}")
    for filename, payload in (validation_documents or {}).items():
        if Path(filename).name != filename or not filename.endswith(".json"):
            raise ValueError(f"Invalid additional validation filename: {filename}")
        write_json(run_dir / "validation" / filename, payload)
        manifest["artifacts"]["canonical"].append(f"validation/{filename}")
