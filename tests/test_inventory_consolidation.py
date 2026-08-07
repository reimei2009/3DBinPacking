from __future__ import annotations

from scipy.optimize import OptimizeResult

from container_packing.algorithms.contracts import AlgorithmOutcome
from container_packing.algorithms.search import (
    BoundedInventoryConsolidator,
    ContainerSearchConfiguration,
    exact_support_closures,
)
from container_packing.algorithms.heuristics.extreme_point_best_fit import (
    solve as solve_best_fit,
)
from container_packing.levels.level_01_validation import validate_solution
from container_packing.algorithms.search.inventory_consolidation import (
    adaptive_cluster_repack_specs,
    rank_destination_compatibility,
)
from container_packing.schemas import Container, Item, Placement, SolveResult


def _outcome(container_ids: tuple[str, ...]) -> AlgorithmOutcome:
    placements = [
        Placement(f"I{index + 1}", container_id, 0, 0, 0, 1, 1, 1, 1)
        for index, container_id in enumerate(container_ids)
    ]
    return AlgorithmOutcome(
        SolveResult("FEASIBLE", "complete", 1.0, None, OptimizeResult()),
        placements,
        "test",
        {},
    )


def _configuration(**consolidation) -> ContainerSearchConfiguration:
    return ContainerSearchConfiguration.from_mapping({
        "enabled": True,
        "initial_used_container_count": 1,
        "max_used_container_count": 3,
        "automatically_increase_container_count": True,
        "consolidation": {
            "enabled": True,
            "time_limit_seconds": 5,
            "max_candidates": 8,
            "item_order_variants": ["current", "decreasing_weight"],
            **consolidation,
        },
    })


def test_consolidation_accepts_only_strictly_better_complete_candidate() -> None:
    items = [Item("I1", 1, 1, 1, 2), Item("I2", 1, 1, 1, 1)]
    containers = [
        Container("C1", 10, 10, 10, 10, 5, volume_m3=0.000001),
        Container("C2", 10, 10, 10, 10, 5, volume_m3=0.000001),
    ]
    baseline = _outcome(("C1", "C2"))

    def executor(items, containers, settings, *, container_subset_policy):
        # Consume one policy candidate so audit counters describe real work.
        next(iter(container_subset_policy.candidates(containers, items)))
        assert "item_order_override" not in settings
        return _outcome(("C1", "C1"))

    result = BoundedInventoryConsolidator().execute(
        baseline=baseline,
        items=items,
        containers=containers,
        settings={},
        search=_configuration(),
        aggregate_lower_bound=1,
        executor=executor,
    )

    assert {value.container_id for value in result.outcome.placements} == {"C1"}
    assert result.metadata["container_consolidation_initial_count"] == 2
    assert result.metadata["container_consolidation_final_count"] == 1
    assert result.metadata["container_consolidation_termination_reason"] == "valid_consolidated"
    assert result.metadata["incumbent_initial_container_count"] == 2
    assert result.metadata["incumbent_final_container_count"] == 1
    assert result.metadata["incumbent_improvement_count"] == 1
    assert result.metadata["incumbent_gap_to_capacity_lower_bound"] == 0


def test_consolidation_does_not_search_below_capacity_lower_bound() -> None:
    called = False

    def executor(*args, **kwargs):
        nonlocal called
        called = True
        return _outcome(("C1",))

    baseline = _outcome(("C1", "C2"))
    result = BoundedInventoryConsolidator().execute(
        baseline=baseline,
        items=[Item("I1", 1, 1, 1, 1), Item("I2", 1, 1, 1, 1)],
        containers=[
            Container("C1", 10, 10, 10, 1, 5, volume_m3=0.000001),
            Container("C2", 10, 10, 10, 1, 5, volume_m3=0.000001),
        ],
        settings={},
        search=_configuration(),
        aggregate_lower_bound=2,
        executor=executor,
    )

    assert called is False
    assert result.outcome is baseline
    assert result.metadata["container_consolidation_termination_reason"] == "already_at_lower_bound"


def test_invalid_or_incomplete_consolidation_candidate_never_replaces_baseline() -> None:
    baseline = _outcome(("C1", "C2"))
    items = [Item("I1", 1, 1, 1, 1), Item("I2", 1, 1, 1, 1)]
    containers = [
        Container("C1", 10, 10, 10, 10, 5, volume_m3=0.000001),
        Container("C2", 10, 10, 10, 10, 5, volume_m3=0.000001),
    ]

    def executor(items, containers, settings, *, container_subset_policy):
        next(iter(container_subset_policy.candidates(containers, items)))
        return AlgorithmOutcome(
            SolveResult("INFEASIBLE_HEURISTIC", "partial", None, None, OptimizeResult()),
            [], "test", {},
        )

    result = BoundedInventoryConsolidator().execute(
        baseline=baseline, items=items, containers=containers, settings={},
        search=_configuration(), aggregate_lower_bound=1, executor=executor,
    )

    assert result.outcome is baseline
    assert result.metadata["container_consolidation_final_count"] == 2
    assert result.metadata["container_consolidation_termination_reason"] == (
        "heuristic_consolidation_failed"
    )
    assert result.metadata["incumbent_final_container_count"] == 2


def test_consolidation_targets_every_cardinality_down_to_capacity_lower_bound() -> None:
    baseline = _outcome(("C1", "C2", "C3", "C4"))
    attempted_cardinalities: list[int] = []
    containers = [
        Container(f"C{index}", 10, 10, 10, 10, 5, volume_m3=0.000001)
        for index in range(1, 5)
    ]

    def executor(items, containers, settings, *, container_subset_policy):
        attempted_cardinalities.append(len(next(iter(
            container_subset_policy.candidates(containers, items)
        ))))
        return baseline

    result = BoundedInventoryConsolidator().execute(
        baseline=baseline,
        items=[Item(f"I{index}", 1, 1, 1, 1) for index in range(1, 5)],
        containers=containers,
        settings={},
        search=_configuration(max_candidates=1),
        aggregate_lower_bound=1,
        executor=executor,
    )

    assert result.metadata["container_consolidation_target_cardinalities"] == [3, 2, 1]
    assert attempted_cardinalities == [3]


def test_seeded_relocation_closes_target_container_and_is_independently_validated() -> None:
    items = [Item("I1", 1, 1, 1, 1), Item("I2", 1, 1, 1, 1)]
    containers = [
        Container("C1", 2, 1, 1, 2, 5, volume_m3=0.000000002),
        Container("C2", 1, 1, 1, 1, 9, volume_m3=0.000000001),
    ]
    baseline = _outcome(("C1", "C2"))
    validated = 0

    def validator(placements):
        nonlocal validated
        validated += 1
        return validate_solution(items, containers, placements).valid

    result = BoundedInventoryConsolidator().execute(
        baseline=baseline,
        items=items,
        containers=containers,
        settings={},
        search=_configuration(container_elimination={
            "enabled": True,
            "maximum_target_containers": 2,
            "maximum_candidates": 8,
            "phase_time_fractions": [0.35, 0.25, 0.40],
            "adaptive_cluster_elimination": {
                "enabled": True,
                "maximum_destination_containers": 2,
                "neighborhood_sizes": [1, 2],
                "beam_width": 4,
                "maximum_candidates": 8,
                "maximum_target_containers": 2,
                "minimum_validation_reserve_seconds": 0,
            },
        }),
        aggregate_lower_bound=1,
        executor=solve_best_fit,
        candidate_validator=validator,
    )

    assert validated >= 1
    assert {value.container_id for value in result.outcome.placements} == {"C1"}
    assert result.metadata["container_elimination_termination_reason"] == (
        "VALID_CLUSTER_ELIMINATION"
    )
    assert result.metadata["container_elimination_closed_container_ids"] == ["C2"]


def test_partial_repack_can_fill_gap_not_reachable_from_seeded_extreme_points() -> None:
    items = [Item("I1", 1, 1, 1, 1), Item("I2", 1, 1, 1, 1)]
    containers = [
        Container("C1", 2, 1, 1, 2, 5, volume_m3=0.000000002),
        Container("C2", 1, 1, 1, 1, 9, volume_m3=0.000000001),
    ]
    baseline = _outcome(("C1", "C2"))

    def executor(items, containers, settings, *, container_subset_policy):
        # Mô phỏng neighborhood bị khóa khi giữ seed. Partial repack phải phá
        # thêm destination item rồi mới gọi canonical Best Fit thành công.
        if settings.get("construction_initial_placements"):
            return AlgorithmOutcome(
                SolveResult(
                    "INFEASIBLE_HEURISTIC", "seeded neighborhood blocked",
                    None, None, OptimizeResult(),
                ),
                [], "test", {},
            )
        return solve_best_fit(
            items, containers, settings,
            container_subset_policy=container_subset_policy,
        )
    result = BoundedInventoryConsolidator().execute(
        baseline=baseline,
        items=items,
        containers=containers,
        settings={},
        search=_configuration(container_elimination={
            "enabled": True,
            "maximum_target_containers": 2,
            "maximum_candidates": 8,
            "phase_time_fractions": [0.35, 0.25, 0.40],
            "adaptive_cluster_elimination": {
                "enabled": True,
                "maximum_destination_containers": 2,
                "neighborhood_sizes": [1, 2],
                "beam_width": 4,
                "maximum_candidates": 8,
                "maximum_target_containers": 2,
                "minimum_validation_reserve_seconds": 0,
            },
        }),
        aggregate_lower_bound=1,
        executor=executor,
        candidate_validator=lambda placements: validate_solution(
            items, containers, placements,
        ).valid,
    )

    assert {value.container_id for value in result.outcome.placements} == {"C1"}
    assert any(
        row.get("accepted") is True and row["phase"] == "partial_repack"
        for row in result.metadata["container_elimination_attempts"]
    )


def test_level2_support_closure_is_transitive() -> None:
    placements = [
        Placement("ROOT", "C1", 0, 0, 0, 2, 2, 1, 1),
        Placement("MIDDLE", "C1", 0, 0, 1, 2, 2, 1, 1),
        Placement("TOP", "C1", 0, 0, 2, 2, 2, 1, 1),
        Placement("LEAF", "C1", 3, 0, 0, 1, 1, 1, 1),
    ]

    closures = exact_support_closures(placements, epsilon_mm=1e-4)

    assert closures["ROOT"] == frozenset({"ROOT", "MIDDLE", "TOP"})
    assert closures["MIDDLE"] == frozenset({"MIDDLE", "TOP"})
    assert closures["TOP"] == frozenset({"TOP"})
    assert closures["LEAF"] == frozenset({"LEAF"})


def test_destination_ranking_and_adaptive_specs_are_deterministic_and_keep_closure() -> None:
    items = {
        value.item_id: value for value in (
            Item("TARGET", 1, 1, 1, 1),
            Item("BLOCKER", 1, 1, 1, 1),
            Item("DEPENDENT", 1, 1, 1, 1),
        )
    }
    placements = [
        Placement("TARGET", "SOURCE", 0, 0, 0, 1, 1, 1, 1),
        Placement("BLOCKER", "D1", 0, 0, 0, 1, 1, 1, 1),
        Placement("DEPENDENT", "D1", 0, 0, 1, 1, 1, 1, 1),
    ]
    destinations = (
        Container("D1", 3, 2, 2, 5, 5, volume_m3=0.000000012),
        Container("D2", 2, 2, 2, 2, 5, volume_m3=0.000000008),
    )
    compatibilities = rank_destination_compatibility(
        target_placements=[placements[0]],
        all_placements=placements,
        containers=destinations,
        item_by_id=items,
        failed_item_id="TARGET",
    )
    assert compatibilities[0].container_id == "D1"

    def closures(values):
        del values
        return {
            "TARGET": frozenset({"TARGET"}),
            "BLOCKER": frozenset({"BLOCKER", "DEPENDENT"}),
            "DEPENDENT": frozenset({"BLOCKER", "DEPENDENT"}),
        }

    first = adaptive_cluster_repack_specs(
        placements=placements,
        target_id="SOURCE",
        compatibilities=compatibilities,
        item_by_id=items,
        support_closure_provider=closures,
        failed_item_id="TARGET",
        maximum_destination_containers=2,
        neighborhood_sizes=(1, 2),
        beam_width=8,
    )
    second = adaptive_cluster_repack_specs(
        placements=placements,
        target_id="SOURCE",
        compatibilities=compatibilities,
        item_by_id=items,
        support_closure_provider=closures,
        failed_item_id="TARGET",
        maximum_destination_containers=2,
        neighborhood_sizes=(1, 2),
        beam_width=8,
    )

    assert [value.signature for value in first] == [
        value.signature for value in second
    ]
    assert first
    assert all(value.neighborhood_size == 2 for value in first)
    assert all(
        {"BLOCKER", "DEPENDENT"}.issubset(value.repack_item_ids)
        for value in first
    )
