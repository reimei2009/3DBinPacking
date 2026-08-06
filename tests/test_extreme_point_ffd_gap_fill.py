from pathlib import Path

from container_packing.algorithms.registry import get_algorithm
from container_packing.algorithms.heuristics.extreme_point_ffd import solve_level1 as solve_ffd
from container_packing.algorithms.heuristics.extreme_point_ffd_gap_fill import solve
from container_packing.algorithms.heuristics.gap_fill import rank_constrained_points
from container_packing.algorithms.heuristics.extreme_point_core import ContainerState, place_item
from container_packing.data_loader import load_config
from container_packing.schemas import Container, Item
from container_packing.levels.level_01_validation import validate_solution


def test_gap_fill_evaluation_checkpoint_keeps_it_hidden_and_not_promoted(
    root: Path,
) -> None:
    definition = get_algorithm("extreme_point_ffd_gap_fill")
    default_config = load_config(root / "config/level_01/default.yaml")
    report = (
        root / "docs/reports/manual/level_01_ep_ffd_gap_fill_baseline_20260805.md"
    ).read_text(encoding="utf-8")

    assert definition.web_visible is False
    assert definition.supported_levels == ("level_01",)
    assert default_config["project"]["algorithm_id"] == "milp_big_m"
    assert "NOT_PROMOTED" in report
    assert "0 WIN / 21 TIE / 2 LOSS" in report


def _container() -> Container:
    return Container("C1", 20, 10, 10, 100, 10, volume_m3=0.000002)


def test_detector_is_deterministic_and_excludes_unopened_containers() -> None:
    state = ContainerState(_container())
    assert rank_constrained_points([state]) == ()
    place_item(state, Item("A", 10, 10, 10, 1), (0, 0, 0), 1e-6)
    assert rank_constrained_points([state]) == rank_constrained_points([state])


def test_gap_fill_is_valid_deterministic_and_keeps_baseline_unchanged() -> None:
    items = [Item("A", 10, 10, 10, 1), Item("B", 10, 10, 10, 1)]
    containers = [_container()]
    baseline = solve_ffd(items, containers)
    first = solve(items, containers)
    second = solve(items, containers)
    assert baseline.placements == solve_ffd(items, containers).placements
    assert first.solve.status == "FEASIBLE"
    assert first.placements == second.placements
    assert validate_solution(items, containers, first.placements).valid
    assert first.metadata["container_subset_policy"] == "fixed_input_subset_v1"
    assert first.metadata["fixed_container_subset_ids"] == ["C1"]
    assert first.metadata["gap_fill_realized_item_order"] == ["A", "B"]
    assert first.metadata["gap_fill_insertions"] == 0


def test_gap_fill_rejects_infeasible_lookahead_candidate() -> None:
    items = [Item("A", 10, 10, 10, 1), Item("TOO_BIG", 21, 10, 10, 1)]
    outcome = solve(items, [_container()])
    assert outcome.solve.status == "INFEASIBLE_HEURISTIC"
    assert outcome.solve.objective_value is None


def test_gap_fill_controlled_fixture_uses_one_container_while_ffd_uses_two() -> None:
    """A small floor-level constrained gap: z=0 must remain eligible."""
    containers = [
        Container("C1", 10, 10, 1, 100, 1, volume_m3=1e-7),
        Container("C2", 10, 10, 1, 100, 2, volume_m3=1e-7),
    ]
    # FFD order: HEAD, NEXT, TALL_GAP, GAP_ITEM.
    items = [
        Item("HEAD", 5, 5, 1, 1),
        Item("NEXT", 6, 4, 1, 1),
        Item("TALL_GAP", 2, 6, 1, 1),
        Item("GAP_ITEM", 2, 2, 1, 1),
    ]
    from container_packing.algorithms.heuristics.container_subset_selection import FixedContainerSubsetSelectionPolicy
    fixed = FixedContainerSubsetSelectionPolicy()
    baseline = solve_ffd(items, containers, container_subset_policy=fixed)
    first = solve(items, containers, container_subset_policy=fixed)
    second = solve(items, containers, container_subset_policy=fixed)

    assert baseline.solve.status == "FEASIBLE"
    assert len({value.container_id for value in baseline.placements}) == 2
    assert first.solve.status == "FEASIBLE"
    assert len({value.container_id for value in first.placements}) == 1
    assert validate_solution(items, containers, first.placements).valid
    assert first.placements == second.placements
    assert first.metadata["gap_fill_realized_item_order"] == [
        "HEAD", "GAP_ITEM", "NEXT", "TALL_GAP",
    ]
    placements = {value.item_id: value for value in first.placements}
    assert (placements["GAP_ITEM"].x_mm, placements["GAP_ITEM"].y_mm) == (5, 0)
    assert (placements["TALL_GAP"].x_mm, placements["TALL_GAP"].y_mm) == (7, 0)
    assert first.metadata["gap_fill_insertions"] == 1
    assert first.metadata["fixed_container_subset_ids"] == ["C1", "C2"]
