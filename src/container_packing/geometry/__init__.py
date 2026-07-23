"""Backend-neutral geometric calculations shared by algorithms and validators."""

from .support import SupportGeometry, evaluate_support, rectangle_union_area
from .orientation import (
    HORIZONTAL_ORIENTATION_CODES,
    ORIENTATION_PROFILE_FIXED,
    ORIENTATION_PROFILE_HORIZONTAL_ROTATABLE,
    ORIENTATION_XYZ,
    ORIENTATION_YXZ,
    OrientedDimensions,
    allowed_orientation_codes,
    oriented_dimensions,
)

__all__ = [
    "HORIZONTAL_ORIENTATION_CODES",
    "ORIENTATION_PROFILE_FIXED",
    "ORIENTATION_PROFILE_HORIZONTAL_ROTATABLE",
    "ORIENTATION_XYZ",
    "ORIENTATION_YXZ",
    "OrientedDimensions",
    "SupportGeometry",
    "allowed_orientation_codes",
    "evaluate_support",
    "oriented_dimensions",
    "rectangle_union_area",
]
