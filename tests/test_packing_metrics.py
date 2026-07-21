from dataclasses import replace

from container_packing.metrics import packing_tiebreak_metrics, placement_signature
from container_packing.schemas import Placement


def test_packing_metrics_and_signature_are_row_order_independent():
    first = Placement("A", "C", 0, 0, 0, 10, 5, 2, 1)
    second = Placement("B", "C", 10, 0, 0, 5, 5, 2, 1)
    placements = [first, second]
    assert packing_tiebreak_metrics(placements) == (150.0, 10.0)
    assert placement_signature(placements) == placement_signature(list(reversed(placements)))
    assert placement_signature(placements) != placement_signature([first, replace(second, x_mm=11)])
