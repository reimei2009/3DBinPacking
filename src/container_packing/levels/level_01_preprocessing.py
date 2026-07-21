"""Level 1 input checks that do not alter item orientation."""

from __future__ import annotations

from ..schemas import Container, Item


def item_fits_container(item: Item, container: Container) -> bool:
    """Return whether the item fits in its current, fixed orientation."""
    return (
        item.length_mm <= container.length_mm
        and item.width_mm <= container.width_mm
        and item.height_mm <= container.height_mm
        and item.weight_kg <= container.max_weight_kg
    )


def validate_instance(items: list[Item], containers: list[Container], *, expected_items: int | None = None) -> None:
    if expected_items is not None and len(items) != expected_items:
        raise ValueError(f"Expected {expected_items} Level 1 items, found {len(items)}")
    available = [container for container in containers if container.availability == 1]
    if not available:
        raise ValueError("No available containers")
    invalid = [item.item_id for item in items if not any(item_fits_container(item, c) for c in available)]
    if invalid:
        raise ValueError(f"Items do not fit any available container without rotation: {', '.join(invalid)}")
