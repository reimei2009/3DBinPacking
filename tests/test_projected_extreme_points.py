from container_packing.algorithms.heuristics.extreme_point_core import (
    ContainerState,
    place_candidate,
)
from container_packing.algorithms.heuristics.extreme_point_projected import (
    solve_best_fit_projected,
    solve_ffd_projected,
)
from container_packing.algorithms.heuristics.projected_extreme_points import (
    ProjectedExtremePointProvider,
)
from container_packing.geometry.orientation import OrientedDimensions
from container_packing.levels.level_01_validation import validate_solution
from container_packing.schemas import Container, Item, Placement


def test_projected_provider_is_deterministic_bounded_and_reports_metadata() -> None:
    container = Container("C1", 10, 10, 10, 100, 1, volume_m3=0.000001)
    state = ContainerState(container)
    place_candidate(
        state,
        Placement("BLOCK", "C1", 0, 0, 0, 4, 4, 4, 1),
        1e-6,
    )
    item = Item("I2", 2, 2, 2, 1)
    dimensions = OrientedDimensions("fixed", 2, 2, 2)
    provider = ProjectedExtremePointProvider()

    first = provider.points(state, item, dimensions)
    second = ProjectedExtremePointProvider().points(state, item, dimensions)

    assert first == second
    assert first
    assert all(0 <= x <= 8 and 0 <= y <= 8 and 0 <= z <= 8 for x, y, z in first)
    assert provider.metadata()["candidate_point_provider"] == "projected_extreme_points_v1"


def test_projected_comparators_are_complete_deterministic_and_independently_valid() -> None:
    items = [Item(f"I{index}", 2, 2, 2, 1) for index in range(1, 5)]
    containers = [Container("C1", 4, 4, 2, 10, 5, volume_m3=0.000000032)]

    for solver in (solve_best_fit_projected, solve_ffd_projected):
        first = solver(items, containers, {"subset_enumeration_limit": 1})
        second = solver(items, containers, {"subset_enumeration_limit": 1})
        assert first.solve.status == "FEASIBLE"
        assert first.placements == second.placements
        assert validate_solution(items, containers, first.placements).valid
        assert first.metadata["candidate_point_provider"] == "projected_extreme_points_v1"


def test_container_state_cached_volume_weight_and_bounds_match_full_recalculation() -> None:
    container = Container("C1", 20, 20, 20, 100, 1, volume_m3=0.000008)
    state = ContainerState(container)
    placements = (
        Placement("I1", "C1", 1, 2, 3, 4, 5, 6, 7),
        Placement("I2", "C1", 8, 1, 2, 3, 4, 5, 11),
    )
    for placement in placements:
        place_candidate(state, placement, 1e-6)

    assert state.loaded_weight_kg == sum(value.weight_kg for value in placements)
    assert state.loaded_volume_mm3 == sum(
        value.length_mm * value.width_mm * value.height_mm for value in placements
    )
    max_x = max(value.x_mm + value.length_mm for value in placements)
    max_y = max(value.y_mm + value.width_mm for value in placements)
    max_z = max(value.z_mm + value.height_mm for value in placements)
    assert (state.max_x_mm, state.max_y_mm, state.max_z_mm) == (max_x, max_y, max_z)
    assert state.bounding_volume_mm3 == max_x * max_y * max_z
