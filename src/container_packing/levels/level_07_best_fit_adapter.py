"""Experimental Level 7 compound-root Best Fit with balance tie-breaking."""

from __future__ import annotations

from typing import Any

from ..algorithms.heuristics.extreme_point_best_fit import solve as solve_best_fit
from ..schemas import Container, Item
from .level_06_compound_adapter import Level06CompoundAdapter, Level06CompoundResult
from .level_07_balance_scoring import BalanceAwareCandidateScoringPolicy
from .level_07_fixture_bundle import balance_rules, validate_level_07_fixture_bundle


def _solve_balance_aware_best_fit(
    items: list[Item], containers: list[Container], settings: dict[str, Any], **kwargs: Any
):
    scoring = BalanceAwareCandidateScoringPolicy(balance_rules(settings))
    return solve_best_fit(
        items, containers, settings,
        candidate_scoring_policy=scoring, **kwargs,
    )


def solve_balance_aware_best_fit_fixture(
    items: list[Item], containers: list[Container], config: dict[str, Any]
) -> Level06CompoundResult:
    return Level06CompoundAdapter(
        "extreme_point_best_fit_balance_fixture",
        "level_07_balance_aware_best_fit_compound_v1",
        _solve_balance_aware_best_fit,
        validate_level_07_fixture_bundle,
    ).solve(items, containers, config)
