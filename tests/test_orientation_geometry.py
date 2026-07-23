"""Tests for the shared horizontal-orientation geometry contract."""

from __future__ import annotations

import pytest

from container_packing.geometry import (
    HORIZONTAL_ORIENTATION_CODES,
    ORIENTATION_PROFILE_FIXED,
    ORIENTATION_PROFILE_HORIZONTAL_ROTATABLE,
    ORIENTATION_XYZ,
    ORIENTATION_YXZ,
    allowed_orientation_codes,
    oriented_dimensions,
)


def test_xyz_orientation_preserves_all_dimensions() -> None:
    result = oriented_dimensions(1200.0, 800.0, 600.0, ORIENTATION_XYZ)

    assert result.code == ORIENTATION_XYZ
    assert result.as_tuple() == (1200.0, 800.0, 600.0)
    assert result.volume_mm3 == 576_000_000.0


def test_yxz_orientation_swaps_only_horizontal_dimensions() -> None:
    original = oriented_dimensions(1200.0, 800.0, 600.0, ORIENTATION_XYZ)
    rotated = oriented_dimensions(1200.0, 800.0, 600.0, ORIENTATION_YXZ)

    assert rotated.code == ORIENTATION_YXZ
    assert rotated.as_tuple() == (800.0, 1200.0, 600.0)
    assert rotated.height_mm == original.height_mm
    assert rotated.volume_mm3 == original.volume_mm3


def test_horizontal_rotatable_profile_is_deduplicated_for_square_base() -> None:
    assert allowed_orientation_codes(
        ORIENTATION_PROFILE_HORIZONTAL_ROTATABLE, 1000.0, 1000.0, 500.0
    ) == (ORIENTATION_XYZ,)


def test_orientation_profiles_have_explicit_canonical_codes() -> None:
    assert HORIZONTAL_ORIENTATION_CODES == (ORIENTATION_XYZ, ORIENTATION_YXZ)
    assert allowed_orientation_codes(ORIENTATION_PROFILE_FIXED, 1200.0, 800.0, 600.0) == (
        ORIENTATION_XYZ,
    )
    assert allowed_orientation_codes(
        ORIENTATION_PROFILE_HORIZONTAL_ROTATABLE, 1200.0, 800.0, 600.0
    ) == HORIZONTAL_ORIENTATION_CODES


@pytest.mark.parametrize(
    ("length_mm", "width_mm", "height_mm"),
    [(0.0, 1.0, 1.0), (-1.0, 1.0, 1.0), (1.0, float("inf"), 1.0)],
)
def test_orientation_rejects_invalid_dimensions(
    length_mm: float, width_mm: float, height_mm: float
) -> None:
    with pytest.raises(ValueError, match="finite and positive"):
        oriented_dimensions(length_mm, width_mm, height_mm, ORIENTATION_XYZ)


def test_orientation_rejects_non_horizontal_code() -> None:
    with pytest.raises(ValueError, match="Only horizontal rotations are active"):
        oriented_dimensions(1200.0, 800.0, 600.0, "XZY")


def test_orientation_profile_rejects_unknown_value() -> None:
    with pytest.raises(ValueError, match="Unknown orientation profile"):
        allowed_orientation_codes("source_forced_orientation", 1200.0, 800.0, 600.0)
