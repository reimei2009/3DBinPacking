import pytest

from container_packing.algorithms.heuristics.construction_strategies import get_construction_strategy


def test_registered_construction_strategies_expose_initial_and_repair_paths() -> None:
    first_fit = get_construction_strategy("extreme_point_ffd")
    best_fit = get_construction_strategy("extreme_point_best_fit")

    assert first_fit.strategy_id == "extreme_point_ffd"
    assert best_fit.strategy_id == "extreme_point_best_fit"
    assert callable(first_fit.solve_initial) and callable(first_fit.pack_repair_order)
    assert callable(best_fit.solve_initial) and callable(best_fit.pack_repair_order)


def test_unknown_construction_strategy_has_actionable_error() -> None:
    with pytest.raises(ValueError, match="Unknown construction strategy"):
        get_construction_strategy("unsupported")
