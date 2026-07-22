import pytest

from container_packing.algorithms.feasibility import (
    ExactSupportFeasibilityPolicy,
    FixedOrientationFeasibilityPolicy,
)
from container_packing.geometry.support import evaluate_support
from container_packing.levels.level_02_algorithms import execute_level_02
from container_packing.levels.level_02_validation import validate_solution
from container_packing.schemas import Container, Item, Placement


def container() -> Container:
    return Container("C", 10, 10, 10, 100, 1, volume_m3=1e-6)


def placement(item_id: str, x: float, y: float, z: float, length: float, width: float, height: float = 5) -> Placement:
    return Placement(item_id, "C", x, y, z, length, width, height, 1)


def allows(policy, candidate, existing=()):
    return policy.allows(
        container(), list(existing), candidate,
        loaded_weight_kg=sum(value.weight_kg for value in existing), tolerance=1e-6,
    )


def test_exact_support_policy_accepts_floor_and_full_single_supporter():
    policy = ExactSupportFeasibilityPolicy(0.8, 1e-4)
    bottom = placement("BOTTOM", 0, 0, 0, 10, 10)
    top = placement("TOP", 0, 0, 5, 10, 10)
    assert allows(policy, bottom)
    assert allows(policy, top, [bottom])


def test_exact_support_geometry_uses_union_of_two_supporters():
    left = placement("LEFT", 0, 0, 0, 5, 10)
    right = placement("RIGHT", 5, 0, 0, 5, 10)
    top = placement("TOP", 0, 0, 5, 10, 10)
    measured = evaluate_support(top, [left, right], epsilon_mm=1e-4)
    assert measured.exact_support_ratio == pytest.approx(1.0)
    assert measured.center_supported
    assert measured.supporting_item_ids == ("LEFT", "RIGHT")


def test_exact_support_policy_rejects_insufficient_area_center_gap_and_wrong_height():
    policy = ExactSupportFeasibilityPolicy(0.8, 1e-4)
    top = placement("TOP", 0, 0, 5, 10, 10)
    half = placement("HALF", 0, 0, 0, 5, 10)
    left_strip = placement("LEFT", 0, 0, 0, 4, 10)
    right_strip = placement("RIGHT", 6, 0, 0, 4, 10)
    wrong_height = placement("LOW", 0, 0, 1, 10, 10, 3)
    assert not allows(policy, top, [half])
    assert not allows(policy, top, [left_strip, right_strip])
    assert not allows(policy, top, [wrong_height])
    assert policy.support_rejected_candidates == 3


@pytest.mark.parametrize("algorithm_id", [
    "extreme_point_ffd",
    "extreme_point_best_fit",
    "extreme_point_hill_climbing",
    "extreme_point_simulated_annealing",
    "maximal_space_best_fit",
])
def test_all_reusable_engines_produce_valid_level2_stack(algorithm_id):
    items = [Item("A", 10, 10, 5, 1), Item("B", 10, 10, 5, 1)]
    settings = {
        "subset_enumeration_limit": 12,
        "subset_candidate_limit": 12,
        "max_iterations": 4,
        "max_neighbors": 8,
        "neighbors_per_iteration": 2,
        "initial_temperature": 0.25,
        "cooling_rate": 0.9,
        "minimum_temperature": 0.001,
        "random_seed": 42,
        "support": {"threshold": 0.8, "epsilon_mm": 1e-4},
    }
    outcome = execute_level_02(algorithm_id, items, [container()], settings)
    checked = validate_solution(items, [container()], outcome.placements)
    assert outcome.solve.status == "FEASIBLE"
    assert checked.result.valid
    assert sorted(value.z_mm for value in outcome.placements) == pytest.approx([0, 5])
    assert outcome.metadata["feasibility_policy"].endswith("exact_support")
    assert outcome.metadata["support_valid_candidates"] > 0


def test_level1_policy_does_not_activate_support_checks():
    policy = FixedOrientationFeasibilityPolicy()
    floating = placement("FLOATING", 0, 0, 5, 2, 2, 2)
    assert allows(policy, floating)
    assert "support_rejected_candidates" not in policy.metadata()


def test_level2_ffd_failure_does_not_fallback_to_another_algorithm():
    oversized = Item("TOO_LARGE", 11, 11, 11, 1)
    outcome = execute_level_02(
        "extreme_point_ffd", [oversized], [container()],
        {"support": {"threshold": 0.8, "epsilon_mm": 1e-4}},
    )
    assert outcome.solve.status == "INFEASIBLE_HEURISTIC"
    assert outcome.backend == "deterministic/extreme-point-ffd"
    assert outcome.placements == []
