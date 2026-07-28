"""Controlled Level 7 balance-aware constructive runtime."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..data_loader import load_config
from ..schemas import ValidationResult
from .level_03_preprocessing import validate_instance
from .level_06_pipeline import _guard as guard_level_06
from .level_07_best_fit_adapter import (
    solve_balance_aware_best_fit,
    solve_balance_aware_best_fit_fixture,
    solve_balance_baseline_best_fit_fixture,
)
from .level_07_ffd_adapter import solve_balance_aware_ffd, solve_balance_aware_ffd_fixture, solve_balance_baseline_ffd_fixture
from .level_07_fixture_bundle import balance_rules, validate_level_07_fixture_bundle
from .load_balance import ContainerBalanceSettings
from .pipeline import LevelRuntimeStrategy, run_configured_level


ALGORITHM_ID = "extreme_point_best_fit_balance_fixture"
BASELINE_ALGORITHM_ID = "extreme_point_best_fit_balance_baseline_fixture"
FFD_ALGORITHM_ID = "extreme_point_ffd_balance_fixture"
FFD_BASELINE_ALGORITHM_ID = "extreme_point_ffd_balance_baseline_fixture"
GENERIC_ALGORITHM_ID = "extreme_point_best_fit_balance"
GENERIC_FFD_ALGORITHM_ID = "extreme_point_ffd_balance"
ALGORITHM_IDS = (
    ALGORITHM_ID, BASELINE_ALGORITHM_ID, FFD_ALGORITHM_ID, FFD_BASELINE_ALGORITHM_ID,
    GENERIC_ALGORITHM_ID, GENERIC_FFD_ALGORITHM_ID,
)


def _guard(config: dict[str, Any]) -> None:
    guard_level_06({
        **config,
        "project": {
            **config.get("project", {}), "level_id": "level_06",
            "algorithm_id": "extreme_point_ffd_nesting_fixture",
        },
    })
    if config.get("project", {}).get("level_id") != "level_07":
        raise ValueError("Level 7 balance runtime requires project.level_id='level_07'")
    if config.get("project", {}).get("algorithm_id") not in ALGORITHM_IDS:
        raise ValueError("Level 7 balance runtime exposes only registered balance-aware algorithms")
    if not bool(config.get("model", {}).get("enforce_balance", False)):
        raise ValueError("Level 7 balance runtime requires model.enforce_balance=true")
    ContainerBalanceSettings.from_config(balance_rules(config))


def _execute(algorithm_id: str, items, containers, settings):
    if algorithm_id == GENERIC_ALGORITHM_ID:
        return solve_balance_aware_best_fit(items, containers, settings).outcome
    if algorithm_id == GENERIC_FFD_ALGORITHM_ID:
        return solve_balance_aware_ffd(items, containers, settings).outcome
    if algorithm_id == ALGORITHM_ID:
        return solve_balance_aware_best_fit_fixture(items, containers, settings).outcome
    if algorithm_id == BASELINE_ALGORITHM_ID:
        return solve_balance_baseline_best_fit_fixture(items, containers, settings).outcome
    if algorithm_id == FFD_ALGORITHM_ID:
        return solve_balance_aware_ffd_fixture(items, containers, settings).outcome
    if algorithm_id == FFD_BASELINE_ALGORITHM_ID:
        return solve_balance_baseline_ffd_fixture(items, containers, settings).outcome
    raise ValueError("Level 7 balance runtime exposes only registered balance-aware algorithms")


STRATEGY = LevelRuntimeStrategy(
    level_number=7,
    execute=_execute,
    validate_instance=lambda items, containers, expected: validate_instance(
        items, containers, expected_items=expected
    ),
    validate_solution=lambda items, containers, placements, config: validate_level_07_fixture_bundle(
        items, containers, placements, config, None
    ),
    guard_config=_guard,
    active_constraints=(
        "compound_boundaries", "compound_payload", "compound_non_overlap",
        "exact_base_support", "base_center_support", "stackability_same_group",
        "maximum_stack_layers", "recursive_static_load_transfer",
        "maximum_supported_weight", "compound_root_center_of_mass_balance",
    ),
    inactive_constraints=(
        "vertical_axis_rotation", "internal_nesting_load_transfer", "pressure",
        "contact_moments", "dynamic_load", "full_physical_stability", "axle_load_limits",
        "floor_zone_load_limits", "door_clearance",
    ),
    metadata_defaults={
        "experimental_runtime": True,
        "runtime_promotion_status": "experimental_dynamic_balance_runtime_not_default",
        "balance_final_validation_required": True,
    },
    algorithm_roles={
        ALGORITHM_ID: "experimental_balance_aware_constructive",
        BASELINE_ALGORITHM_ID: "experimental_balance_baseline_comparator",
        FFD_ALGORITHM_ID: "experimental_balance_aware_first_fit",
        FFD_BASELINE_ALGORITHM_ID: "experimental_balance_first_fit_baseline_comparator",
        GENERIC_ALGORITHM_ID: "experimental_balance_aware_practical_candidate",
        GENERIC_FFD_ALGORITHM_ID: "experimental_balance_aware_fast_comparator",
    },
)


def run_from_config(
    config_path: str | Path, *, item_count: int | None = None,
    container_count: int | None = None, write_outputs: bool = True,
    level_id: str = "level_07", algorithm_id: str = ALGORITHM_ID,
    environment: str = "local", random_seed: int | None = None,
    algorithm_parameters: dict[str, Any] | None = None,
    config_overrides: dict[str, Any] | None = None,
    item_selection_strategy: str | None = None, item_selection_seed: int | None = None,
):
    overrides = dict(config_overrides or {})
    overrides["project"] = {**dict(overrides.get("project", {})), "algorithm_id": algorithm_id}
    return run_configured_level(
        config_path, strategy=STRATEGY, item_count=item_count, container_count=container_count,
        write_outputs=write_outputs, level_id=level_id, algorithm_id=algorithm_id,
        environment=environment, random_seed=random_seed,
        algorithm_parameters=algorithm_parameters, config_overrides=overrides,
        item_selection_strategy=item_selection_strategy, item_selection_seed=item_selection_seed,
    )
