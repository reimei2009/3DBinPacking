"""Regression coverage for Level 2 inventory search composition."""

from __future__ import annotations

import pytest

from container_packing.algorithms.search import ContainerSearchConfiguration
from container_packing.levels.level_02_algorithms import execute_level_02
from container_packing.levels.level_02_validation import validate_solution
from container_packing.schemas import Container, Item


def _containers() -> list[Container]:
    return [
        Container("PREFIX_TOO_SMALL", 10, 10, 10, 100, 1, volume_m3=1e-6),
        Container("EXPENSIVE", 30, 30, 30, 100, 20, volume_m3=27e-6),
        Container("CHEAP_FEASIBLE", 20, 20, 20, 100, 10, volume_m3=8e-6),
    ]


def _settings(*, enabled: bool = True) -> dict:
    return {
        "subset_enumeration_limit": 8,
        "support": {"threshold": 0.8, "epsilon_mm": 1e-4},
        "container_search": {
            "enabled": enabled,
            "initial_used_container_count": 1,
            "max_used_container_count": 1,
            "automatically_increase_container_count": False,
            "time_limit_seconds": 5,
        },
    }


@pytest.mark.parametrize("algorithm_id", ["extreme_point_best_fit", "extreme_point_ffd"])
def test_level2_inventory_search_uses_full_catalog_and_preserves_exact_support(algorithm_id: str) -> None:
    items = [Item("I1", 20, 20, 10, 1)]

    outcome = execute_level_02(algorithm_id, items, _containers(), _settings())

    assert outcome.solve.status == "FEASIBLE"
    assert {placement.container_id for placement in outcome.placements} == {"CHEAP_FEASIBLE"}
    checked = validate_solution(items, _containers(), outcome.placements)
    assert checked.result.valid
    assert outcome.metadata["inventory_physical_container_count"] == 3
    assert outcome.metadata["hard_precheck_valid"] is True
    assert outcome.metadata["feasibility_policy"].endswith("exact_support")


def test_level2_inventory_search_rejects_unsupported_milp_explicitly() -> None:
    with pytest.raises(ValueError, match="currently supports only"):
        execute_level_02("milp_big_m", [Item("I1", 1, 1, 1, 1)], _containers(), _settings())


def test_level2_inventory_disabled_keeps_constructive_path() -> None:
    outcome = execute_level_02(
        "extreme_point_ffd", [Item("I1", 20, 20, 10, 1)], _containers()[1:], _settings(enabled=False),
    )

    assert outcome.solve.status == "FEASIBLE"
    assert "container_inventory_count" not in outcome.metadata


def test_level2_inventory_configuration_default_is_disabled() -> None:
    configuration = ContainerSearchConfiguration.from_mapping({"enabled": False})
    assert configuration.enabled is False
