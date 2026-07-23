"""Pure horizontal-orientation geometry shared by future packing levels.

The source 3DBPPsi data permits rotations only in the horizontal plane. The
vertical axis is therefore invariant: this module intentionally exposes only
``XYZ`` and ``YXZ`` and does not model the other four cuboid rotations.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


ORIENTATION_XYZ = "XYZ"
"""Keep the source dimensions as ``(length, width, height)``."""

ORIENTATION_YXZ = "YXZ"
"""Swap horizontal axes to ``(width, length, height)``."""

HORIZONTAL_ORIENTATION_CODES = (ORIENTATION_XYZ, ORIENTATION_YXZ)

ORIENTATION_PROFILE_FIXED = "fixed"
ORIENTATION_PROFILE_HORIZONTAL_ROTATABLE = "horizontal_rotatable"


@dataclass(frozen=True)
class OrientedDimensions:
    """Dimensions resulting from one permitted horizontal orientation."""

    code: str
    length_mm: float
    width_mm: float
    height_mm: float

    @property
    def volume_mm3(self) -> float:
        """Return the cuboid volume, unchanged by horizontal rotation."""

        return self.length_mm * self.width_mm * self.height_mm

    def as_tuple(self) -> tuple[float, float, float]:
        """Return dimensions in canonical ``(length, width, height)`` order."""

        return (self.length_mm, self.width_mm, self.height_mm)


def oriented_dimensions(
    length_mm: float,
    width_mm: float,
    height_mm: float,
    orientation_code: str,
) -> OrientedDimensions:
    """Apply one supported orientation while preserving the vertical dimension.

    Raises:
        ValueError: If dimensions are not finite and positive, or the code is
            not one of the two horizontal-orientation codes.
    """

    _validate_dimensions(length_mm, width_mm, height_mm)
    _validate_orientation_code(orientation_code)
    if orientation_code == ORIENTATION_XYZ:
        return OrientedDimensions(ORIENTATION_XYZ, length_mm, width_mm, height_mm)
    return OrientedDimensions(ORIENTATION_YXZ, width_mm, length_mm, height_mm)


def allowed_orientation_codes(
    profile: str,
    length_mm: float,
    width_mm: float,
    height_mm: float,
) -> tuple[str, ...]:
    """Return deduplicated orientation codes for an explicit synthetic profile.

    This deliberately does not infer a profile from the source
    ``forced_orientation`` field. Its semantics remain inactive until a later
    level defines and validates a source-backed mapping.
    """

    _validate_dimensions(length_mm, width_mm, height_mm)
    if profile == ORIENTATION_PROFILE_FIXED:
        return (ORIENTATION_XYZ,)
    if profile == ORIENTATION_PROFILE_HORIZONTAL_ROTATABLE:
        if length_mm == width_mm:
            return (ORIENTATION_XYZ,)
        return HORIZONTAL_ORIENTATION_CODES
    allowed_profiles = (
        f"{ORIENTATION_PROFILE_FIXED!r}, "
        f"{ORIENTATION_PROFILE_HORIZONTAL_ROTATABLE!r}"
    )
    raise ValueError(f"Unknown orientation profile {profile!r}. Expected one of: {allowed_profiles}.")


def _validate_orientation_code(orientation_code: str) -> None:
    if orientation_code not in HORIZONTAL_ORIENTATION_CODES:
        allowed = ", ".join(HORIZONTAL_ORIENTATION_CODES)
        raise ValueError(
            f"Unsupported orientation code {orientation_code!r}. "
            f"Only horizontal rotations are active: {allowed}."
        )


def _validate_dimensions(length_mm: float, width_mm: float, height_mm: float) -> None:
    dimensions = {
        "length_mm": length_mm,
        "width_mm": width_mm,
        "height_mm": height_mm,
    }
    invalid = [name for name, value in dimensions.items() if not isfinite(value) or value <= 0]
    if invalid:
        details = ", ".join(f"{name}={dimensions[name]!r}" for name in invalid)
        raise ValueError(f"Orientation dimensions must be finite and positive; invalid: {details}.")
