"""Level 3 input checks for the declared horizontal-orientation profile."""

from __future__ import annotations

from ..algorithms.orientation import horizontal_orientation_provider
from ..schemas import Container, Item


def item_fits_container(item: Item, container: Container) -> bool:
    """Return whether at least one allowed horizontal orientation fits."""
    return any(
        dimensions.length_mm <= container.length_mm
        and dimensions.width_mm <= container.width_mm
        and dimensions.height_mm <= container.height_mm
        and item.weight_kg <= container.max_weight_kg
        for dimensions in horizontal_orientation_provider().candidates(item)
    )


def validate_instance(
    items: list[Item], containers: list[Container], *, expected_items: int | None = None
) -> None:
    if expected_items is not None and len(items) != expected_items:
        raise ValueError(f"Expected {expected_items} Level 3 items, found {len(items)}")
    available = [container for container in containers if container.availability == 1]
    if not available:
        raise ValueError("No available containers")
    invalid = [item.item_id for item in items if not any(item_fits_container(item, value) for value in available)]
    if invalid:
        raise ValueError(
            "Items do not fit any available container in an allowed horizontal orientation: "
            + ", ".join(invalid)
        )
