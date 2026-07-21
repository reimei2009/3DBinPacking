"""Backend-independent metrics calculated from canonical placements."""

from __future__ import annotations

from hashlib import sha256
import json

from ..schemas import Placement


def packing_tiebreak_metrics(placements: list[Placement]) -> tuple[float, float]:
    """Return occupied bounding volume and coordinate compactness."""
    used_ids = {value.container_id for value in placements}
    bounding_volume = 0.0
    coordinate_score = 0.0
    for container_id in sorted(used_ids):
        values = [value for value in placements if value.container_id == container_id]
        max_x = max(value.x_mm + value.length_mm for value in values)
        max_y = max(value.y_mm + value.width_mm for value in values)
        max_z = max(value.z_mm + value.height_mm for value in values)
        bounding_volume += max_x * max_y * max_z
        coordinate_score += sum(value.x_mm + value.y_mm + value.z_mm for value in values)
    return bounding_volume, coordinate_score


def placement_signature(placements: list[Placement]) -> str:
    """Hash the complete canonical placement geometry independent of row order."""
    rows = sorted((
        value.item_id, value.container_id,
        value.x_mm, value.y_mm, value.z_mm,
        value.length_mm, value.width_mm, value.height_mm, value.weight_kg,
    ) for value in placements)
    payload = json.dumps(rows, separators=(",", ":"), ensure_ascii=True)
    return sha256(payload.encode("utf-8")).hexdigest()
