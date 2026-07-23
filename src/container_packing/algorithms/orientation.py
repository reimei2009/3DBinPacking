"""Orientation providers consumed by generic constructive algorithms."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ..geometry.orientation import (
    ORIENTATION_PROFILE_FIXED,
    ORIENTATION_PROFILE_HORIZONTAL_ROTATABLE,
    OrientedDimensions,
    allowed_orientation_codes,
    oriented_dimensions,
)
from ..schemas import Item


class OrientationProvider(Protocol):
    """Supplies allowed, canonical dimensions for one item."""

    provider_id: str

    def candidates(self, item: Item) -> tuple[OrientedDimensions, ...]: ...

    def metadata(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ProfileOrientationProvider:
    """Build orientation candidates from a declared profile, not dataset guesses."""

    profile: str = ORIENTATION_PROFILE_FIXED
    provider_id: str = "fixed_orientation_provider"

    def candidates(self, item: Item) -> tuple[OrientedDimensions, ...]:
        return tuple(
            oriented_dimensions(item.length_mm, item.width_mm, item.height_mm, code)
            for code in allowed_orientation_codes(
                self.profile, item.length_mm, item.width_mm, item.height_mm
            )
        )

    def metadata(self) -> dict[str, Any]:
        return {"orientation_provider": self.provider_id, "orientation_profile": self.profile}


def fixed_orientation_provider() -> ProfileOrientationProvider:
    """Return the backward-compatible provider used by Levels 1 and 2."""

    return ProfileOrientationProvider()


def horizontal_orientation_provider() -> ProfileOrientationProvider:
    """Return the planned Level 3 `XYZ`/`YXZ` provider."""

    return ProfileOrientationProvider(
        profile=ORIENTATION_PROFILE_HORIZONTAL_ROTATABLE,
        provider_id="horizontal_orientation_provider",
    )
