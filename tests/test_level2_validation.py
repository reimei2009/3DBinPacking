from container_packing.levels.level_02_validation import rectangle_union_area, validate_solution
from container_packing.schemas import Container, Item, Placement


def test_exact_union_area_does_not_double_count_overlapping_rectangles():
    assert rectangle_union_area([(0, 0, 6, 10), (4, 0, 10, 10)]) == 100


def test_validator_rejects_half_supported_floating_item():
    items = [Item("BOTTOM", 5, 10, 5, 1), Item("TOP", 10, 10, 5, 1)]
    containers = [Container("C", 10, 10, 10, 10, 1, volume_m3=1e-6)]
    placements = [
        Placement("BOTTOM", "C", 0, 0, 0, 5, 10, 5, 1),
        Placement("TOP", "C", 0, 0, 5, 10, 10, 5, 1),
    ]
    checked = validate_solution(items, containers, placements, support_threshold=0.8)
    codes = {issue.code for issue in checked.result.issues}
    top = next(value for value in checked.support_records if value.item_id == "TOP")
    assert "INSUFFICIENT_SUPPORT_RATIO" in codes
    assert top.exact_support_ratio == 0.5


def test_validator_rejects_item_without_top_face_contact():
    items = [Item("A", 5, 5, 2, 1)]
    containers = [Container("C", 10, 10, 10, 10, 1, volume_m3=1e-6)]
    placements = [Placement("A", "C", 0, 0, 3, 5, 5, 2, 1)]
    checked = validate_solution(items, containers, placements)
    assert {"UNSUPPORTED_ITEM", "INSUFFICIENT_SUPPORT_RATIO", "CENTER_NOT_SUPPORTED"} <= {
        issue.code for issue in checked.result.issues
    }

