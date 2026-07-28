"""Experimental Level 7 compound-root FFD balance A/B fixtures."""

from __future__ import annotations

from typing import Any

from ..algorithms.heuristics.extreme_point_ffd import solve as solve_ffd
from ..schemas import Container, Item
from .level_06_compound_adapter import Level06CompoundAdapter, Level06CompoundResult
from .level_07_ffd_selection import BalanceAwareFirstFitCandidateSelection
from .level_07_fixture_bundle import balance_rules, validate_level_07_fixture_bundle
from .level_07_two_stage import solve_two_stage_balance


def _solve_balance_aware_ffd_fixture(
    items: list[Item], containers: list[Container], settings: dict[str, Any], **kwargs: Any
):
    """Preserve the frozen A/B fixture candidate set for regression evidence."""
    selector = BalanceAwareFirstFitCandidateSelection(balance_rules(settings))
    return solve_ffd(items, containers, settings, candidate_selection_policy=selector, **kwargs)


def solve_balance_aware_ffd(
    items: list[Item], containers: list[Container], config: dict[str, Any]
) -> Level06CompoundResult:
    """Generic balance-aware First Fit over explicit-or-empty compound roots."""
    return solve_two_stage_balance(
        items, containers, config, algorithm_id="extreme_point_ffd_balance",
        baseline_solver=solve_ffd,
    )


def solve_balance_aware_ffd_fixture(
    items: list[Item], containers: list[Container], config: dict[str, Any]
) -> Level06CompoundResult:
    return Level06CompoundAdapter(
        "extreme_point_ffd_balance_fixture",
        "level_07_balance_aware_ffd_compound_v1",
        _solve_balance_aware_ffd_fixture,
        validate_level_07_fixture_bundle,
    ).solve(items, containers, config)


def solve_balance_baseline_ffd_fixture(
    items: list[Item], containers: list[Container], config: dict[str, Any]
) -> Level06CompoundResult:
    result = Level06CompoundAdapter(
        "extreme_point_ffd_balance_baseline_fixture",
        "level_07_balance_baseline_ffd_compound_v1",
        solve_ffd,
        validate_level_07_fixture_bundle,
    ).solve(items, containers, config)
    result.outcome.metadata.update({
        "first_fit_candidate_selection_policy": "extreme_point_first_fit_default_v1",
        "balance_construction_mode": "first_feasible_container_baseline_final_validation_hard",
        "balance_container_selection_scope": "first_feasible_container_only",
    })
    return result
