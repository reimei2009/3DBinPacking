from __future__ import annotations

from time import perf_counter

from container_packing.algorithms.feasibility import FixedOrientationFeasibilityPolicy
from container_packing.data_loader import load_config
from container_packing.levels.level_07_fixture_bundle import balance_rules
from container_packing.levels.level_08_container_elimination import (
    DeliveryContainerEliminationLns,
    _support_components,
)
from container_packing.levels.unloading import UnloadingSettings
from container_packing.schemas import Container, Item, Placement


def _item(item_id: str, length: float) -> Item:
    return Item(
        item_id, length, 10, 10, 1,
        source={
            "delivery_priority": 1,
            "delivery_stop_id": "STOP-A",
            "delivery_data_source": "test",
        },
    )


def _container(container_id: str) -> Container:
    return Container(container_id, 300, 100, 100, 100, 1)


def test_support_components_keep_supporter_and_dependent_together() -> None:
    placements = [
        Placement("ROOT", "C1", 0, 0, 0, 100, 100, 20, 2),
        Placement("TOP", "C1", 0, 0, 20, 100, 100, 20, 1),
        Placement("OTHER", "C1", 150, 0, 0, 50, 50, 20, 1),
    ]

    components = _support_components(placements, 1e-6)

    assert [{value.item_id for value in group} for group in components] == [
        {"OTHER"}, {"ROOT", "TOP"},
    ]


def test_conflict_neighborhood_can_close_fragmented_donor_container(root) -> None:
    items = [_item("A", 150), _item("B", 100), _item("C", 50)]
    containers = [_container("C1"), _container("C2")]
    placements = [
        Placement("A", "C1", 0, 0, 0, 150, 10, 10, 1),
        Placement("B", "C2", 50, 0, 0, 100, 10, 10, 1),
        Placement("C", "C2", 200, 0, 0, 50, 10, 10, 1),
    ]
    config = load_config(root / "config/level_08/default.yaml")
    unloading = UnloadingSettings.from_config(
        load_config(root / "config/level_08/unloading_rules.yaml")
    )
    engine = DeliveryContainerEliminationLns(
        policy=FixedOrientationFeasibilityPolicy(),
        unloading_settings=unloading,
        balance_config=balance_rules(config),
        tolerance_mm=1e-6,
        support_epsilon_mm=1e-6,
        neighborhood_sizes=(2,),
        max_candidates=128,
        points_per_group=24,
    )

    result = engine.eliminate(
        items, containers, placements,
        donor_ids=["C1"],
        validate_final=lambda values: (
            len(values) == 3
            and {value.container_id for value in values} == {"C2"}
        ),
        deadline=perf_counter() + 2,
    )

    assert result.placements is not None
    assert result.termination_reason == "container_eliminated"
    assert result.selected_neighborhood_size == 2
    assert {value.container_id for value in result.placements} == {"C2"}
