"""Focused tests for bounded local Level 7 COG repair."""

from __future__ import annotations

from pathlib import Path
from copy import deepcopy

import pytest

from container_packing.algorithms.feasibility import FixedOrientationFeasibilityPolicy
from container_packing.data_loader import load_config
from container_packing.levels.level_07_balance_repair import (
    BalanceMomentCache,
    BalanceRepairEngine,
    RootMassProperties,
    support_closures,
    _contributors,
)
from container_packing.levels.level_07_balance_lns import (
    BalanceLnsEngine,
    _closure_neighborhood,
)
from container_packing.levels.level_07_two_stage import _consolidate_extra_container
from container_packing.schemas import Container, Item, Placement


def _container(container_id: str = "C1") -> Container:
    return Container(container_id, 1000, 1000, 1000, 1000, 100)


def _balance_config(root: Path) -> dict:
    return load_config(root / "config/level_07/balance_rules.yaml")


def test_default_local_repair_budget_is_bounded(root: Path) -> None:
    config = load_config(root / "config/level_07/default.yaml")
    for algorithm_id in (
        "extreme_point_best_fit_balance", "extreme_point_ffd_balance"
    ):
        values = config["algorithms"][algorithm_id]
        assert values["balance_repair_time_limit_seconds"] == 45
        assert values["balance_repair_fixed_subset_seconds"] == 10
        assert values["balance_repair_lns_seconds"] == 30
        assert values["balance_repair_extra_container_seconds"] == 5
        assert values["balance_repair_max_candidates"] == 4096
        assert values["balance_repair_contributor_limit"] == 12
        assert values["balance_repair_max_extra_containers"] == 1
        assert values["balance_repair_lns_max_candidates"] == 8192
        assert values["balance_repair_lns_neighborhood_sizes"] == [4, 8, 12]
        assert values["balance_repair_extra_max_candidates"] == 8192


def test_cached_cog_delta_matches_full_recalculation(root: Path) -> None:
    container = _container()
    before = Placement("I1", "C1", 0, 0, 0, 100, 100, 100, 10)
    after = Placement("I1", "C1", 450, 450, 0, 100, 100, 100, 10)
    cache = BalanceMomentCache.from_placements([before])

    changed = cache.changed([before], [after])
    rebuilt = BalanceMomentCache.from_placements([after])

    assert changed.values["C1"] == pytest.approx(rebuilt.values["C1"])
    assert changed.score({"C1": container}, _balance_config(root)) == pytest.approx(
        rebuilt.score({"C1": container}, _balance_config(root))
    )


def test_contributors_focus_worst_container_and_axis(root: Path) -> None:
    first = _container("C1")
    second = _container("C2")
    config = deepcopy(_balance_config(root))
    placements = [
        Placement("C1_EDGE", "C1", 300, 300, 0, 100, 100, 100, 100),
        Placement("C2_HEAVY_EDGE", "C2", 0, 0, 0, 100, 100, 100, 200),
        Placement("C2_CENTER", "C2", 450, 450, 0, 100, 100, 100, 10),
    ]

    contributors = _contributors(
        placements, [first, second], config, limit=2
    )

    assert contributors[0] == "C2_HEAVY_EDGE"
    assert all(value.startswith("C2_") for value in contributors)


def test_compound_mass_offset_is_used_instead_of_envelope_center() -> None:
    root = Placement("ROOT", "C1", 100, 200, 0, 400, 300, 100, 30)
    cache = BalanceMomentCache.from_placements(
        [root], {"ROOT": RootMassProperties(30, 80, 60)}
    )

    assert cache.values["C1"] == pytest.approx([
        30, 30 * (100 + 80), 30 * (200 + 60)
    ])


def test_support_closure_never_leaves_supported_item_behind() -> None:
    supporter = Placement("ROOT", "C1", 0, 0, 0, 100, 100, 100, 10)
    child = Placement("TOP", "C1", 0, 0, 100, 100, 100, 50, 5)

    closures = support_closures([supporter, child], epsilon_mm=1e-6)

    assert closures["ROOT"] == {"ROOT", "TOP"}
    assert closures["TOP"] == {"TOP"}


def test_local_relocation_repairs_cog_without_opening_container(root: Path) -> None:
    container = _container()
    item = Item("I1", 100, 100, 100, 10)
    initial = Placement("I1", "C1", 0, 0, 0, 100, 100, 100, 10)
    balance_config = _balance_config(root)
    engine = BalanceRepairEngine(
        policy=FixedOrientationFeasibilityPolicy(),
        balance_config=balance_config,
        coordinate_tolerance_mm=1e-6,
        support_epsilon_mm=1e-6,
        max_candidates=16,
        contributor_limit=4,
    )

    def valid(values: list[Placement]) -> bool:
        return (
            BalanceMomentCache.from_placements(values).score(
                {"C1": container}, balance_config
            )[0]
            <= 1e-12
        )

    result = engine.repair(
        [item], [container], [initial], validate_candidate=valid,
        fixed_seconds=1, extra_seconds=0, extra_containers=[],
    )

    assert result.placements is not None
    assert result.opened_extra_containers == 0
    assert result.placements[0].x_mm == pytest.approx(450)
    assert result.stats.accepted_moves == ["relocate"]
    assert result.stats.termination_reason == "fixed_subset_valid"


def test_repair_accepts_physical_intermediate_before_final_balance(root: Path) -> None:
    container = _container()
    config = deepcopy(_balance_config(root))
    config["balance_profile"]["max_longitudinal_offset_ratio"] = 0.0
    config["balance_profile"]["max_lateral_offset_ratio"] = 0.0
    items = [Item("I1", 100, 100, 100, 10), Item("I2", 100, 100, 100, 10)]
    initial = [
        Placement("I1", "C1", 0, 450, 0, 100, 100, 100, 10),
        Placement("I2", "C1", 100, 450, 0, 100, 100, 100, 10),
    ]
    engine = BalanceRepairEngine(
        policy=FixedOrientationFeasibilityPolicy(), balance_config=config,
        coordinate_tolerance_mm=1e-6, support_epsilon_mm=1e-6,
        max_candidates=128, contributor_limit=4,
    )
    final = lambda values: BalanceMomentCache.from_placements(values).score(
        {"C1": container}, config
    )[0] <= 1e-12

    result = engine.repair(
        items, [container], initial, validate_candidate=lambda _: True,
        validate_final_candidate=final, fixed_seconds=1,
        extra_seconds=0, extra_containers=[],
    )

    assert result.placements is not None
    assert result.best_feasible_placements == result.placements
    assert final(list(result.placements))
    assert len(result.stats.accepted_moves) >= 2


def test_deadline_uses_injected_clock_without_sleep(root: Path) -> None:
    ticks = iter((0.0, 1.0, 2.0, 3.0, 4.0))
    engine = BalanceRepairEngine(
        policy=FixedOrientationFeasibilityPolicy(),
        balance_config=_balance_config(root),
        coordinate_tolerance_mm=1e-6,
        support_epsilon_mm=1e-6,
        max_candidates=16,
        contributor_limit=4,
        clock=lambda: next(ticks),
    )
    initial = Placement("I1", "C1", 0, 0, 0, 100, 100, 100, 10)

    result = engine.repair(
        [Item("I1", 100, 100, 100, 10)], [_container()], [initial],
        validate_candidate=lambda _: False,
        fixed_seconds=0, extra_seconds=0, extra_containers=[],
    )

    assert result.placements is None
    assert result.best_feasible_placements == (initial,)
    assert result.stats.candidates_evaluated == 0
    assert result.stats.termination_reason == "deadline"


def test_extra_container_is_considered_only_after_fixed_phase(root: Path) -> None:
    balance_config = deepcopy(_balance_config(root))
    profile = balance_config["balance_profile"]
    profile["target_longitudinal_ratio"] = 0.8
    profile["target_lateral_ratio"] = 0.5
    profile["max_longitudinal_offset_ratio"] = 0.05
    profile["max_lateral_offset_ratio"] = 0.05
    fixed = Container("C1", 100, 100, 100, 1000, 100)
    extra = Container("C2", 1000, 100, 100, 1000, 200)
    item = Item("I1", 100, 100, 100, 10)
    initial = Placement("I1", "C1", 0, 0, 0, 100, 100, 100, 10)
    engine = BalanceRepairEngine(
        policy=FixedOrientationFeasibilityPolicy(),
        balance_config=balance_config,
        coordinate_tolerance_mm=1e-6,
        support_epsilon_mm=1e-6,
        max_candidates=32,
        contributor_limit=4,
    )

    def valid(values: list[Placement]) -> bool:
        maps = {"C1": fixed, "C2": extra}
        return BalanceMomentCache.from_placements(values).score(
            maps, balance_config
        )[0] <= 1e-12

    result = engine.repair(
        [item], [fixed], [initial], validate_candidate=valid,
        fixed_seconds=1, extra_seconds=1, extra_containers=[extra],
    )

    assert result.placements is not None
    assert result.opened_extra_containers == 1
    assert result.placements[0].container_id == "C2"
    assert result.stats.termination_reason == "extra_container_valid"


def test_rescue_container_consolidation_closes_extra_when_possible(
    root: Path,
) -> None:
    fixed = _container("C1")
    extra = _container("C2")
    item = Item("I1", 100, 100, 100, 10)
    initial = [Placement("I1", "C2", 450, 450, 0, 100, 100, 100, 10)]
    config = load_config(root / "config/level_07/default.yaml")

    consolidated, metadata = _consolidate_extra_container(
        [item], [fixed, extra], initial, extra_container_id="C2",
        policy=FixedOrientationFeasibilityPolicy(), config=config,
        mass_properties={},
        validate_candidate=lambda values: (
            len(values) == 1 and values[0].container_id == "C1"
        ),
        deadline=10**12,
    )

    assert consolidated is not None
    assert {value.container_id for value in consolidated} == {"C1"}
    assert metadata["balance_consolidation_result"] == "extra_container_eliminated"


def test_lns_repacks_small_neighborhood_to_repair_balance(root: Path) -> None:
    container = _container()
    balance_config = deepcopy(_balance_config(root))
    balance_config["balance_profile"]["max_longitudinal_offset_ratio"] = 0.1
    items = [Item("I1", 100, 100, 100, 10), Item("I2", 100, 100, 100, 10)]
    initial = [
        Placement("I1", "C1", 0, 0, 0, 100, 100, 100, 10),
        Placement("I2", "C1", 100, 0, 0, 100, 100, 100, 10),
    ]
    engine = BalanceLnsEngine(
        policy=FixedOrientationFeasibilityPolicy(), balance_config=balance_config,
        coordinate_tolerance_mm=1e-6, support_epsilon_mm=1e-6,
        max_candidates=96, neighborhood_size=2,
        affected_container_limit=1, max_rounds=2,
    )

    result = engine.repair(
        items, [container], initial,
        validate_candidate=lambda values: BalanceMomentCache.from_placements(values).score(
            {"C1": container}, balance_config
        )[0] <= 1e-12,
        time_limit_seconds=1,
    )

    assert result.placements is not None
    assert result.stats.termination_reason == "accepted_valid_neighborhood"
    assert result.stats.candidates_evaluated > 0


def test_lns_neighborhood_targets_moment_contributor(root: Path) -> None:
    container = _container()
    balance_config = deepcopy(_balance_config(root))
    placements = [
        Placement("HEAVY_CENTER", "C1", 450, 450, 0, 100, 100, 100, 100),
        Placement("LIGHT_EDGE", "C1", 0, 0, 0, 100, 100, 100, 10),
        Placement("HEAVY_EDGE", "C1", 100, 0, 0, 100, 100, 100, 80),
    ]
    closures = {value.item_id: {value.item_id} for value in placements}

    neighborhood = _closure_neighborhood(
        placements, closures, [container], {}, balance_config, 2
    )

    assert [group[0].item_id for group in neighborhood] == [
        "HEAVY_EDGE", "LIGHT_EDGE"
    ]


def test_lns_adaptive_sizes_are_deterministic(root: Path) -> None:
    container = _container()
    config = deepcopy(_balance_config(root))
    placements = [
        Placement(f"I{index}", "C1", index * 100, 0, 0, 100, 100, 100, 10)
        for index in range(4)
    ]
    items = [Item(value.item_id, 100, 100, 100, 10) for value in placements]
    engine = BalanceLnsEngine(
        policy=FixedOrientationFeasibilityPolicy(), balance_config=config,
        coordinate_tolerance_mm=1e-6, support_epsilon_mm=1e-6,
        max_candidates=256, neighborhood_size=2, neighborhood_sizes=(2, 3),
        affected_container_limit=1, max_rounds=1,
    )

    first = engine.repair(
        items, [container], placements,
        validate_candidate=lambda _: False, time_limit_seconds=1,
    )
    second = engine.repair(
        items, [container], placements,
        validate_candidate=lambda _: False, time_limit_seconds=1,
    )

    assert first.stats.neighborhood_sizes_attempted == [2, 3]
    assert second.stats.neighborhood_sizes_attempted == [2, 3]
    assert first.stats.destroyed_item_ids == second.stats.destroyed_item_ids


def test_lns_deadline_uses_fake_clock_without_sleep(root: Path) -> None:
    class FakeClock:
        value = -0.05

        def __call__(self) -> float:
            self.value += 0.05
            return self.value

    container = _container()
    config = deepcopy(_balance_config(root))
    placements = [
        Placement("I1", "C1", 0, 0, 0, 100, 100, 100, 10),
        Placement("I2", "C1", 100, 0, 0, 100, 100, 100, 10),
    ]
    engine = BalanceLnsEngine(
        policy=FixedOrientationFeasibilityPolicy(), balance_config=config,
        coordinate_tolerance_mm=1e-6, support_epsilon_mm=1e-6,
        max_candidates=100, neighborhood_size=2,
        affected_container_limit=1, max_rounds=10, clock=FakeClock(),
    )

    result = engine.repair(
        [Item("I1", 100, 100, 100, 10), Item("I2", 100, 100, 100, 10)],
        [container], placements, validate_candidate=lambda _: False,
        time_limit_seconds=0.1,
    )

    assert result.placements is None
    assert result.stats.termination_reason == "deadline"
