"""Registry-driven CLI shared by every implemented level and algorithm."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys

from .algorithms.registry import list_algorithms
from .application.failure_explanation import explain_failure
from .data_loader import DataValidationError, load_config
from .experiments.contracts import ExperimentRequest
from .experiments.runner import prepare_experiment, run_experiment
from .instance_data import ITEM_SELECTION_STRATEGIES
from .levels.registry import get_level, list_levels
from .reporting import validation_payload
from .runtime.inputs import positive_int, prompt_choice, prompt_positive
from .runtime.project import find_project_root
from .schemas import RunResult


def _positive(value: str) -> int:
    try:
        return positive_int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _non_negative(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be an integer") from exc
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def _request_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--level", dest="level_id", help="Implemented level ID, e.g. level_01")
    parser.add_argument("--algorithm", dest="algorithm_id", help="Implemented algorithm ID")
    parser.add_argument("--config", type=Path, help="Level configuration; defaults through the level registry")
    parser.add_argument("--items-count", type=_positive)
    parser.add_argument("--containers-count", type=_positive)
    parser.add_argument("--seed", type=_non_negative, help="Override project.random_seed for this run")
    parser.add_argument("--item-selection", choices=ITEM_SELECTION_STRATEGIES, help="Deterministic item subset policy")
    parser.add_argument("--selection-seed", type=_non_negative, help="Subset seed; required by stable_random")
    parser.add_argument("--environment", choices=("local", "colab", "kaggle"), default=None)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--interactive", action="store_true", help="Prompt for all experiment inputs")
    mode.add_argument("--non-interactive", action="store_true", help="Use flags/config defaults without prompts")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="container-packing")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List runnable levels and algorithms")
    run = commands.add_parser("run", help="Prepare, solve, validate, and report an experiment")
    _request_arguments(run)
    run.add_argument("--preview-limit", type=_non_negative, default=20, help="Placement rows shown in terminal; 0 hides them")
    run.add_argument("--json-only", action="store_true", help="Print metadata JSON only for automation")
    prepare = commands.add_parser("prepare", help="Prepare processed data without solving")
    _request_arguments(prepare)
    validate = commands.add_parser("validate", help="Independently validate one completed run")
    validate.add_argument("--level", dest="level_id", help="Optional expected level ID")
    validate.add_argument("--run-dir", type=Path, required=True)
    return parser


def _resolve_request(args: argparse.Namespace) -> ExperimentRequest:
    level_ids = tuple(value.level_id for value in list_levels())
    interactive = bool(args.interactive or (not args.non_interactive and sys.stdin.isatty()))
    level_id = args.level_id or level_ids[0]
    if interactive:
        level_id = prompt_choice("Level", level_ids, level_id)
    level = get_level(level_id)
    selected_config = args.config or level.default_config
    config_path = selected_config.resolve() if selected_config.is_absolute() else (find_project_root() / selected_config).resolve()
    config = load_config(config_path)
    algorithm_ids = tuple(value.algorithm_id for value in list_algorithms(level_id=level_id))
    configured_algorithm = str(config.get("project", {}).get("algorithm_id", algorithm_ids[0]))
    if configured_algorithm not in algorithm_ids:
        raise ValueError(f"Configured algorithm {configured_algorithm!r} is not compatible with {level_id}")
    algorithm_id = args.algorithm_id or configured_algorithm
    if interactive:
        algorithm_id = prompt_choice("Algorithm", algorithm_ids, algorithm_id)
    if args.config is None:
        selected_config = level.config_for_algorithm(algorithm_id)
        config_path = (
            selected_config.resolve() if selected_config.is_absolute()
            else (find_project_root() / selected_config).resolve()
        )
        config = load_config(config_path)
    defaults = config["instance"]
    item_count = args.items_count or int(defaults["item_count"])
    container_count = args.containers_count or int(defaults["container_count"])
    environment = args.environment or "local"
    item_selection = args.item_selection or str(defaults.get("item_selection_strategy", "prefix"))
    selection_seed = args.selection_seed if args.selection_seed is not None else defaults.get("item_selection_seed")
    exact_reference_limit = _exact_reference_item_limit(algorithm_id, config)
    if interactive and exact_reference_limit is not None:
        print(
            f"Exact MILP reference limit: at most {exact_reference_limit} items. "
            "Use a heuristic such as extreme_point_ffd for practical runs."
        )
    fixed_fixture = _fixed_fixture_inputs(config)
    if interactive and fixed_fixture is not None:
        _reject_conflicting_fixture_flags(args, fixed_fixture)
        print(
            "Fixed fixture inputs: "
            f"items={fixed_fixture['item_count']}, containers={fixed_fixture['container_count']}, "
            f"environment={fixed_fixture['environment']}, selection={fixed_fixture['item_selection_strategy']}."
        )
        item_count = fixed_fixture["item_count"]
        container_count = fixed_fixture["container_count"]
        environment = fixed_fixture["environment"]
        item_selection = fixed_fixture["item_selection_strategy"]
        selection_seed = fixed_fixture["item_selection_seed"]
    elif interactive:
        item_count = prompt_positive("Number of items", item_count)
        container_count = prompt_positive("Number of containers", container_count)
        environment = prompt_choice("Environment", ("local", "colab", "kaggle"), environment)
        item_selection = prompt_choice("Item selection", ITEM_SELECTION_STRATEGIES, item_selection)
        if item_selection == "stable_random":
            selection_seed = prompt_positive(
                "Item-selection seed", int(selection_seed if selection_seed is not None else 42)
            )
    if exact_reference_limit is not None and item_count > exact_reference_limit:
        raise ValueError(
            f"Exact MILP reference is limited to {exact_reference_limit} items; received {item_count}. "
            "Use extreme_point_ffd for practical runs."
        )
    return ExperimentRequest(
        level_id=level_id, algorithm_id=algorithm_id, config_path=config_path,
        item_count=item_count, container_count=container_count, environment=environment,
        random_seed=args.seed,
        item_selection_strategy=item_selection,
        item_selection_seed=selection_seed,
    )


def _fixed_fixture_inputs(config: dict) -> dict[str, object] | None:
    """Read optional frozen input values from a versioned fixture config."""
    fixture = config.get("fixture")
    if not isinstance(fixture, dict):
        return None
    required = (
        "required_item_count", "required_container_count", "required_environment",
        "required_item_selection_strategy", "required_item_selection_seed",
    )
    if not all(key in fixture for key in required):
        return None
    return {
        "item_count": int(fixture["required_item_count"]),
        "container_count": int(fixture["required_container_count"]),
        "environment": str(fixture["required_environment"]),
        "item_selection_strategy": str(fixture["required_item_selection_strategy"]),
        "item_selection_seed": fixture["required_item_selection_seed"],
    }


def _exact_reference_item_limit(algorithm_id: str, config: dict) -> int | None:
    """Return a configured exact-reference cap without constraining other MILP levels."""
    if algorithm_id != "milp_big_m":
        return None
    value = config.get("solver", {}).get("orientation_reference_max_items")
    return None if value is None else int(value)


def _reject_conflicting_fixture_flags(args: argparse.Namespace, fixed: dict[str, object]) -> None:
    """Fail early when an explicit interactive flag conflicts with a frozen fixture."""
    comparisons = (
        ("--items-count", args.items_count, fixed["item_count"]),
        ("--containers-count", args.containers_count, fixed["container_count"]),
        ("--environment", args.environment, fixed["environment"]),
        ("--item-selection", args.item_selection, fixed["item_selection_strategy"]),
        ("--selection-seed", args.selection_seed, fixed["item_selection_seed"]),
    )
    for flag, value, expected in comparisons:
        if value is not None and value != expected:
            raise ValueError(f"Frozen fixture requires {flag}={expected!r}; got {value!r}")


def _list_payload() -> dict:
    return {
        "levels": [{
            "level_id": value.level_id, "description": value.description,
            "supported_algorithms": list(value.supported_algorithms),
        } for value in list_levels()],
        "algorithms": [{
            "algorithm_id": value.algorithm_id, "family": value.family,
            "supported_levels": list(value.supported_levels),
            "local_friendly": value.local_friendly, "gpu_recommended": value.gpu_recommended,
        } for value in list_algorithms()],
    }


def terminal_preview(result: RunResult, *, placement_limit: int = 20) -> str:
    """Create a compact, dependency-free result preview for humans."""
    metadata = result.metadata
    validation = "NOT_RUN" if result.validation is None else ("VALID" if result.validation.valid else "INVALID")
    selected = ", ".join(metadata.get("selected_containers", [])) or "none"
    lines = [
        "\n=== EXPERIMENT PREVIEW ===",
        f"Status       : {metadata.get('status')}",
        f"Validation   : {validation}",
        f"Level        : {metadata.get('level_id')}",
        f"Algorithm    : {metadata.get('algorithm_id')}",
        f"Algorithm role: {metadata.get('algorithm_role') or 'research_method'}",
        f"Items        : {metadata.get('n_items')}",
        f"Item subset  : {metadata.get('item_selection_strategy', 'prefix')}",
        f"Subset seed  : {metadata.get('item_selection_seed')}",
        f"Containers   : {metadata.get('container_count', 0)} used / {metadata.get('n_containers')} available",
        f"Selected     : {selected}",
        f"Objective    : {metadata.get('objective_value')}",
        f"Algorithm time: {float(metadata.get('algorithm_runtime_seconds', 0.0)):.3f} s",
        f"Run directory: {metadata.get('run_dir')}",
    ]
    failure = explain_failure(metadata, language="vi")
    if failure is not None:
        lines.extend([
            "",
            "FAILURE DIAGNOSTICS",
            f"Class        : {failure.failure_class}",
            f"Reason       : {failure.title}",
            f"Explanation  : {failure.summary}",
        ])
        lines.extend(f"Evidence     : {value}" for value in failure.evidence)
        lines.extend(f"Suggestion   : {value}" for value in failure.suggestions)
    if metadata.get("mip_gap") is not None:
        lines.append(f"MIP gap      : {100 * float(metadata['mip_gap']):.3f}%")
    if metadata.get("mip_dual_bound") is not None:
        lines.append(f"Best bound   : {float(metadata['mip_dual_bound']):.6g}")
    if metadata.get("mip_node_count") is not None:
        lines.append(f"MIP nodes    : {int(metadata['mip_node_count'])}")
    if metadata.get("support_enabled"):
        lines.extend([
            f"Support threshold: {metadata.get('support_threshold')}",
            f"Minimum exact support ratio: {metadata.get('minimum_exact_support_ratio')}",
            f"All centers supported: {metadata.get('all_centers_supported')}",
        ])
    if metadata.get("container_elimination_enabled"):
        lines.append(
            "Container elimination: "
            f"{metadata.get('container_elimination_initial_count', 0)} -> "
            f"{metadata.get('container_elimination_final_count', 0)}, "
            f"{metadata.get('container_elimination_candidates_evaluated', 0)} candidate(s), "
            f"stop={metadata.get('container_elimination_termination_reason', 'unknown')}"
        )
        if metadata.get("adaptive_cluster_elimination_enabled"):
            lines.append(
                "Adaptive cluster: neighborhoods="
                f"{metadata.get('adaptive_cluster_neighborhood_sizes_attempted', [])}, "
                "failed_targets="
                f"{len(metadata.get('adaptive_cluster_failed_items_by_target', {}))}, "
                "duplicate_skipped="
                f"{metadata.get('adaptive_cluster_duplicate_candidates_skipped', 0)}"
            )
    if metadata.get("container_consolidation_enabled"):
        lines.append(
            "Incumbent improvement: "
            f"{metadata.get('incumbent_initial_container_count', 0)} -> "
            f"{metadata.get('incumbent_final_container_count', 0)}, "
            f"lower_bound={metadata.get('container_consolidation_aggregate_lower_bound')}, "
            f"stop={metadata.get('container_consolidation_termination_reason', 'unknown')}"
        )
    if metadata.get("load_bearing_enabled"):
        lines.extend([
            f"Load capacity profile: {metadata.get('load_bearing_capacity_profile')}",
            f"Maximum load utilization: {metadata.get('maximum_load_utilization_ratio')}",
            f"Minimum load safety margin: {metadata.get('minimum_load_safety_margin_kg')} kg",
            f"Load-transfer edges: {metadata.get('load_transfer_edge_count')}",
        ])
    if metadata.get("nesting_runtime_enabled"):
        relation_count = int(metadata.get("nesting_relation_count", 0) or 0)
        compound_count = int(metadata.get("compound_count", 0) or 0)
        relation_note = "declared relation(s) selected" if relation_count else "no compatible declared relation in selected input"
        lines.extend([
            f"Nesting relations: {relation_count} ({relation_note})",
            f"Compound envelopes: {compound_count}",
            f"Maximum nesting depth: {metadata.get('maximum_nesting_depth', 0)}",
        ])
    if metadata.get("center_of_mass_model"):
        lines.extend([
            f"Balance profile: {metadata.get('balance_profile')}",
            f"COG validation: {metadata.get('balance_validation_status')}",
            f"Balanced containers: {metadata.get('balanced_container_count', 0)} balanced / "
            f"{metadata.get('unbalanced_container_count', 0)} unbalanced",
        ])
    if metadata.get("balance_pipeline_runtime_seconds") is not None:
        lines.append(
            "Balance phases: baseline "
            f"{float(metadata.get('balance_baseline_runtime_seconds', 0.0)):.3f} s, "
            "repair "
            f"{float(metadata.get('balance_repair_runtime_seconds', 0.0)):.3f} s, "
            f"{int(metadata.get('balance_repair_attempts', 0))} candidate(s), "
            f"stop={metadata.get('balance_repair_termination_reason', 'unknown')}"
        )
    if metadata.get("balance_lns_runtime_seconds") is not None:
        lines.append(
            "Balance LNS: "
            f"{float(metadata['balance_lns_runtime_seconds']):.3f} s, "
            f"{int(metadata.get('balance_lns_candidates_evaluated', 0))} candidate(s), "
            f"stop={metadata.get('balance_lns_termination_reason', 'unknown')}"
        )
    if metadata.get("balance_failure_reason"):
        lines.append(f"Balance failure: {metadata['balance_failure_reason']}")
    if metadata.get("balance_outcome_class"):
        lines.append(f"Balance outcome: {metadata['balance_outcome_class']}")
    if result.placements:
        groups: dict[str, list] = defaultdict(list)
        for placement in result.placements:
            groups[placement.container_id].append(placement)
        lines.extend(["", "CONTAINER LOAD PREVIEW", "ID       ITEMS   WEIGHT_KG   VOLUME_M3"])
        for container_id in sorted(groups):
            values = groups[container_id]
            lines.append(
                f"{container_id:<8} {len(values):>5}   "
                f"{sum(value.weight_kg for value in values):>9.3f}   "
                f"{sum(value.volume_m3 for value in values):>9.4f}"
            )
    shown = result.placements[:placement_limit]
    if shown:
        lines.extend(["", f"PLACEMENTS (showing {len(shown)}/{len(result.placements)})", "ITEM       CONT       X_MM       Y_MM       Z_MM       LxWxH_MM"])
        for value in shown:
            dimensions = f"{value.length_mm:g}x{value.width_mm:g}x{value.height_mm:g}"
            lines.append(
                f"{value.item_id:<10} {value.container_id:<7} {value.x_mm:>10.2f} "
                f"{value.y_mm:>10.2f} {value.z_mm:>10.2f}   {dimensions}"
            )
        if len(result.placements) > placement_limit:
            lines.append(f"... {len(result.placements) - placement_limit} rows hidden; see solution/placements.csv")
    elif result.placements and placement_limit == 0:
        lines.extend(["", "Placement preview disabled; see solution/placements.csv."])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "list":
            print(json.dumps(_list_payload(), indent=2)); return 0
        if args.command == "validate":
            manifest = json.loads((args.run_dir / "manifest.json").read_text(encoding="utf-8"))
            manifest_level = str(manifest["level"])
            if args.level_id is not None and args.level_id != manifest_level:
                raise ValueError(
                    f"Requested level {args.level_id!r} does not match run manifest level {manifest_level!r}"
                )
            result = get_level(manifest_level).validate_run(args.run_dir)
            print(json.dumps(validation_payload(result), indent=2)); return 0 if result.valid else 3
        request = _resolve_request(args)
        if args.command == "prepare":
            print(json.dumps(prepare_experiment(request), indent=2)); return 0
        result = run_experiment(request)
        if args.json_only:
            print(json.dumps(result.metadata, indent=2))
        else:
            print(terminal_preview(result, placement_limit=args.preview_limit))
        return 0 if result.validation is not None and result.validation.valid else 2
    except (DataValidationError, KeyError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr); return 2


if __name__ == "__main__":
    raise SystemExit(main())
