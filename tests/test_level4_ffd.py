from __future__ import annotations

from pathlib import Path

import pytest

from container_packing.data_loader import load_config
from container_packing.algorithms.feasibility import ExactSupportFeasibilityPolicy
from container_packing.algorithms.heuristics.construction_strategies import get_construction_strategy
from container_packing.algorithms.heuristics.extreme_point_neighborhood import RepackingStats, repack_neighbor
from container_packing.levels.level_04_algorithms import ExactSupportStackabilityPolicy, execute_level_04
from container_packing.levels.level_04_validation import validate_solution
from container_packing.levels.stackability import StackabilitySettings, attributes_for_item, infer_parent_relations
from container_packing.schemas import Container, Item, Placement


def _item(item_id: str, maximum: int = 2, code: str = "1") -> Item:
    return Item(item_id, 10, 10, 5, 1, source={
        "stackability_code": code, "max_stackability": str(maximum),
    })


def _settings(root: Path) -> dict:
    return {
        "coordinate_tolerance_mm": 1e-6,
        "subset_enumeration_limit": 4,
        "subset_candidate_limit": 4,
        "max_iterations": 2,
        "max_neighbors": 4,
        "neighbors_per_iteration": 2,
        "initial_temperature": 0.25,
        "cooling_rate": 0.9,
        "minimum_temperature": 0.001,
        "random_seed": 42,
        "support": {"threshold": 1.0, "epsilon_mm": 1e-4},
        "stackability": load_config(root / "config/level_04/stackability_rules.yaml"),
    }


@pytest.mark.parametrize("algorithm_id", [
    "extreme_point_ffd", "extreme_point_best_fit", "extreme_point_hill_climbing",
    "extreme_point_simulated_annealing",
    "maximal_space_best_fit",
])
def test_level4_constructive_solver_builds_a_valid_declared_stack(root: Path, algorithm_id: str) -> None:
    items = [_item("A"), _item("B")]
    containers = [Container("C", 10, 10, 10, 10, 1, volume_m3=1e-6)]
    settings = _settings(root)

    outcome = execute_level_04(algorithm_id, items, containers, settings)
    stack_settings = StackabilitySettings.from_config(settings["stackability"])
    attributes = {item.item_id: attributes_for_item(item, stack_settings) for item in items}
    relations = infer_parent_relations(outcome.placements, attributes, epsilon_mm=1e-4)
    checked = validate_solution(items, containers, outcome.placements, relations, settings["stackability"], support_threshold=1.0)

    assert outcome.solve.status == "FEASIBLE"
    assert checked.result.valid
    assert len(relations) == 1
    assert outcome.metadata["stackability_rejected_candidates"] >= 0


@pytest.mark.parametrize("algorithm_id", [
    "extreme_point_ffd", "extreme_point_best_fit", "extreme_point_hill_climbing",
    "extreme_point_simulated_annealing",
    "maximal_space_best_fit",
])
def test_level4_constructive_solver_rejects_stack_above_declared_cap(
    root: Path, algorithm_id: str,
) -> None:
    items = [_item("A"), _item("B"), _item("C")]
    containers = [Container("C", 10, 10, 15, 10, 1, volume_m3=1.5e-6)]

    outcome = execute_level_04(algorithm_id, items, containers, _settings(root))

    assert outcome.solve.status == "INFEASIBLE_HEURISTIC"
    assert outcome.metadata["stackability_rejected_candidates"] > 0


def test_level4_hill_climbing_uses_best_fit_for_zero_iteration_baseline(root: Path) -> None:
    items = [_item("A"), _item("B")]
    containers = [Container("C", 10, 10, 10, 10, 1, volume_m3=1e-6)]
    settings = _settings(root)
    settings.update({"max_iterations": 0, "max_neighbors": 4, "subset_candidate_limit": 4})

    best_fit = execute_level_04("extreme_point_best_fit", items, containers, settings)
    first = execute_level_04("extreme_point_hill_climbing", items, containers, settings)
    second = execute_level_04("extreme_point_hill_climbing", items, containers, settings)

    assert first.solve.status == "FEASIBLE"
    assert first.placements == best_fit.placements == second.placements
    assert first.metadata["initial_constructor"] == "extreme_point_best_fit"
    assert first.metadata["repair_constructor"] == "extreme_point_best_fit"
    assert first.metadata["hill_climbing_iterations"] == 0
    assert first.metadata["feasible_neighbors"] == 0
    assert first.metadata["rejected_neighbors"] == 0


def test_level4_simulated_annealing_uses_best_fit_for_zero_iteration_baseline(root: Path) -> None:
    items = [_item("A"), _item("B")]
    containers = [Container("C", 10, 10, 10, 10, 1, volume_m3=1e-6)]
    settings = _settings(root)
    settings["max_iterations"] = 0

    best_fit = execute_level_04("extreme_point_best_fit", items, containers, settings)
    first = execute_level_04("extreme_point_simulated_annealing", items, containers, settings)
    second = execute_level_04("extreme_point_simulated_annealing", items, containers, settings)

    assert first.solve.status == "FEASIBLE"
    assert first.placements == best_fit.placements == second.placements
    assert first.metadata["initial_constructor"] == "extreme_point_best_fit"
    assert first.metadata["repair_constructor"] == "extreme_point_best_fit"
    assert first.metadata["annealing_iterations"] == 0


def test_level4_best_fit_repair_rejects_neighbor_above_stack_cap(root: Path) -> None:
    items = [_item("A"), _item("B"), _item("C")]
    containers = [Container("C", 10, 10, 15, 10, 1, volume_m3=1.5e-6)]
    settings = _settings(root)
    stack_settings = StackabilitySettings.from_config(settings["stackability"])
    policy = ExactSupportStackabilityPolicy(
        attributes={item.item_id: attributes_for_item(item, stack_settings) for item in items},
        epsilon_mm=1e-4,
        base=ExactSupportFeasibilityPolicy(1.0, 1e-4),
    )

    repaired = repack_neighbor(
        items, containers, [
            Placement("A", "C", 0, 0, 0, 10, 10, 5, 1),
            Placement("B", "C", 0, 0, 5, 10, 10, 5, 1),
        ], settings, RepackingStats(), policy,
        construction_strategy=get_construction_strategy("extreme_point_best_fit"),
    )

    assert repaired is None
    assert policy.stackability_rejected_candidates > 0
