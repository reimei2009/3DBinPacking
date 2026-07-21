import pytest

from container_packing.schemas import Placement
from container_packing.levels.level_01_validation import boxes_intersect


def box(x=0, y=0, z=0, length=10, width=10, height=10, item="A"):
    return Placement(item, "C", x, y, z, length, width, height, 1)


@pytest.mark.parametrize("second", [box(x=11), box(y=11), box(z=11), box(x=10), box(x=10, y=10)])
def test_separated_or_touching_boxes_do_not_intersect(second):
    assert not boxes_intersect(box(), second)


@pytest.mark.parametrize("second", [box(x=9), box(x=2, y=2, z=2, length=2, width=2, height=2), box()])
def test_overlapping_boxes_intersect(second):
    assert boxes_intersect(box(), second)
