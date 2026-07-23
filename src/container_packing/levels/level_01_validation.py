"""Independent validation of placements, separate from MILP constraints."""

from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations

from ..geometry.orientation import allowed_orientation_codes, oriented_dimensions
from ..schemas import Container, Item, Placement, ValidationIssue, ValidationResult


def boxes_intersect(a: Placement, b: Placement, eps: float = 1e-4) -> bool:
    separated = (
        a.x_mm + a.length_mm <= b.x_mm + eps or b.x_mm + b.length_mm <= a.x_mm + eps
        or a.y_mm + a.width_mm <= b.y_mm + eps or b.y_mm + b.width_mm <= a.y_mm + eps
        or a.z_mm + a.height_mm <= b.z_mm + eps or b.z_mm + b.height_mm <= a.z_mm + eps
    )
    return not separated


def validate_solution(
    items: list[Item], containers: list[Container], placements: list[Placement],
    *, coordinate_tolerance: float = 1e-4, weight_tolerance: float = 1e-6,
    orientation_profile: str = "fixed",
) -> ValidationResult:
    """Independently validate placements for an explicit orientation profile.

    Levels 1 and 2 retain the default ``fixed`` profile.  The optional
    horizontal profile is an inactive, reusable validation seam for a future
    level; it does not activate rotation in either existing level.
    """
    issues: list[ValidationIssue] = []
    item_map = {item.item_id: item for item in items}
    container_map = {container.container_id: container for container in containers}
    counts = Counter(placement.item_id for placement in placements)
    for item_id in sorted(item_map):
        if counts[item_id] == 0:
            issues.append(ValidationIssue("MISSING_ITEM", f"Item {item_id} is missing", (item_id,)))
        elif counts[item_id] > 1:
            issues.append(ValidationIssue("DUPLICATE_ITEM", f"Item {item_id} appears {counts[item_id]} times", (item_id,)))
    for item_id in sorted(set(counts) - set(item_map)):
        issues.append(ValidationIssue("UNKNOWN_ITEM", f"Unknown item {item_id}", (item_id,)))

    by_container: dict[str, list[Placement]] = defaultdict(list)
    for placement in placements:
        item = item_map.get(placement.item_id)
        container = container_map.get(placement.container_id)
        if container is None:
            issues.append(ValidationIssue("UNKNOWN_CONTAINER", f"Unknown container {placement.container_id}", (placement.item_id,), placement.container_id))
            continue
        by_container[placement.container_id].append(placement)
        if item is None:
            continue
        allowed_codes = allowed_orientation_codes(
            orientation_profile, item.length_mm, item.width_mm, item.height_mm
        )
        if placement.orientation_code not in allowed_codes:
            allowed = ", ".join(allowed_codes)
            issues.append(ValidationIssue(
                "UNSUPPORTED_ORIENTATION",
                f"{placement.item_id}: orientation {placement.orientation_code!r} is not allowed; expected one of {allowed}",
                (placement.item_id,),
                placement.container_id,
            ))
        else:
            expected = oriented_dimensions(
                item.length_mm, item.width_mm, item.height_mm, placement.orientation_code
            )
            for field, expected_value in zip(
                ("length_mm", "width_mm", "height_mm"), expected.as_tuple(), strict=True
            ):
                if abs(getattr(placement, field) - expected_value) > coordinate_tolerance:
                    issues.append(ValidationIssue(
                        "DIMENSION_MISMATCH",
                        f"{placement.item_id}: {field} does not match orientation {placement.orientation_code}",
                        (placement.item_id,),
                        placement.container_id,
                    ))
        if abs(placement.weight_kg - item.weight_kg) > weight_tolerance:
            issues.append(ValidationIssue("WEIGHT_MISMATCH", f"{placement.item_id}: weight does not match input", (placement.item_id,), placement.container_id))
        if min(placement.x_mm, placement.y_mm, placement.z_mm) < -coordinate_tolerance:
            issues.append(ValidationIssue("NEGATIVE_COORDINATE", f"{placement.item_id} has a negative coordinate", (placement.item_id,), placement.container_id))
        limits = (
            (placement.x_mm + placement.length_mm, container.length_mm, "length"),
            (placement.y_mm + placement.width_mm, container.width_mm, "width"),
            (placement.z_mm + placement.height_mm, container.height_mm, "height"),
        )
        for end, limit, axis in limits:
            if end > limit + coordinate_tolerance:
                issues.append(ValidationIssue("OUT_OF_BOUNDS", f"{placement.item_id} exceeds container {axis}", (placement.item_id,), placement.container_id))

    for container_id, group in by_container.items():
        container = container_map[container_id]
        loaded_weight = sum(placement.weight_kg for placement in group if placement.item_id in item_map)
        if loaded_weight > container.max_weight_kg + weight_tolerance:
            issues.append(ValidationIssue("OVERWEIGHT", f"{container_id} load {loaded_weight} exceeds {container.max_weight_kg}", container_id=container_id))
        for first, second in combinations(group, 2):
            if boxes_intersect(first, second, coordinate_tolerance):
                issues.append(ValidationIssue("OVERLAP", f"{first.item_id} overlaps {second.item_id}", (first.item_id, second.item_id), container_id))
    return ValidationResult(valid=not issues, issues=issues)
