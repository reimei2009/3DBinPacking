"""Registry-driven CLI shared by every implemented level and algorithm."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys

from .algorithms.registry import list_algorithms
from .data_loader import DataValidationError, load_config
from .experiments.contracts import ExperimentRequest
from .experiments.runner import prepare_experiment, run_experiment
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
    defaults = config["instance"]
    item_count = args.items_count or int(defaults["item_count"])
    container_count = args.containers_count or int(defaults["container_count"])
    environment = args.environment or "local"
    if interactive:
        item_count = prompt_positive("Number of items", item_count)
        container_count = prompt_positive("Number of containers", container_count)
        environment = prompt_choice("Environment", ("local", "colab", "kaggle"), environment)
    return ExperimentRequest(
        level_id=level_id, algorithm_id=algorithm_id, config_path=config_path,
        item_count=item_count, container_count=container_count, environment=environment,
        random_seed=args.seed,
    )


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
        f"Items        : {metadata.get('n_items')}",
        f"Containers   : {metadata.get('container_count', 0)} used / {metadata.get('n_containers')} available",
        f"Selected     : {selected}",
        f"Objective    : {metadata.get('objective_value')}",
        f"Algorithm time: {float(metadata.get('algorithm_runtime_seconds', 0.0)):.3f} s",
        f"Run directory: {metadata.get('run_dir')}",
    ]
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
