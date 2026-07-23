"""Independent orientation-plus-support validation for the planned Level 3."""

from __future__ import annotations

from container_packing.levels.level_03_validation import validate_solution
from container_packing.schemas import Container, Item, Placement


def test_horizontal_rotation_and_exact_support_are_validated_together() -> None:
    items = [Item("BOTTOM", 10, 20, 5, 1), Item("TOP", 10, 20, 5, 1)]
    containers = [Container("C", 20, 20, 10, 10, 1, volume_m3=0.000004)]
    placements = [
        Placement("BOTTOM", "C", 0, 0, 0, 20, 10, 5, 1, "YXZ"),
        Placement("TOP", "C", 0, 0, 5, 20, 10, 5, 1, "YXZ"),
    ]

    checked = validate_solution(items, containers, placements)

    assert checked.result.valid
    assert checked.orientation_profile == "horizontal_rotatable"
    assert [record.exact_support_ratio for record in checked.support_records] == [1.0, 1.0]


def test_level3_validator_rejects_height_axis_rotation() -> None:
    items = [Item("A", 10, 20, 5, 1)]
    containers = [Container("C", 20, 20, 10, 10, 1, volume_m3=0.000004)]
    placements = [Placement("A", "C", 0, 0, 0, 5, 20, 10, 1, "XZY")]

    checked = validate_solution(items, containers, placements)

    assert "UNSUPPORTED_ORIENTATION" in {issue.code for issue in checked.result.issues}
