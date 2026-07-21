from dataclasses import replace

from container_packing.schemas import Container, Item, Placement
from container_packing.levels.level_01_validation import validate_solution


def fixture():
    items = [Item("A", 10, 10, 10, 2), Item("B", 10, 10, 10, 3)]
    containers = [Container("C", 20, 10, 10, 5, 1, volume_m3=0.000002)]
    placements = [Placement("A", "C", 0, 0, 0, 10, 10, 10, 2), Placement("B", "C", 10, 0, 0, 10, 10, 10, 3)]
    return items, containers, placements


def test_valid_touching_solution():
    assert validate_solution(*fixture()).valid


def test_detects_overlap():
    items, containers, placements = fixture(); placements[1] = replace(placements[1], x_mm=9)
    assert "OVERLAP" in {issue.code for issue in validate_solution(items, containers, placements).issues}


def test_detects_missing_duplicate_unknown_bounds_and_weight():
    items, containers, placements = fixture()
    bad = [replace(placements[0], x_mm=-1, weight_kg=99), placements[0], replace(placements[1], item_id="X")]
    codes = {issue.code for issue in validate_solution(items, containers, bad).issues}
    assert {"DUPLICATE_ITEM", "MISSING_ITEM", "UNKNOWN_ITEM", "NEGATIVE_COORDINATE", "WEIGHT_MISMATCH", "OVERWEIGHT"} <= codes
