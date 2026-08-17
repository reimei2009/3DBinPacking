"""Deterministic broad-phase lookup for top-face support contacts.

The index is deliberately not an authority for contact geometry.  It only
reduces the placements passed to :func:`contact_rectangle`; independent
validators continue to use the brute-force path.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right, insort
from dataclasses import dataclass

from ..schemas import Placement
from .support import contact_rectangle

CONTACT_SUPPORT_INDEX_VERSION = "top_face_xy_broad_phase_v1"


@dataclass
class ContactSupportIndexStats:
    queries: int = 0
    placements_examined: int = 0
    brute_force_placements: int = 0
    committed_placements: int = 0

    @property
    def estimated_scans_avoided(self) -> int:
        return max(0, self.brute_force_placements - self.placements_examined)

    def metadata(self, *, enabled: bool) -> dict[str, object]:
        return {
            "contact_support_index_enabled": enabled,
            "contact_support_index_version": (
                CONTACT_SUPPORT_INDEX_VERSION if enabled else "disabled"
            ),
            "contact_support_index_queries": self.queries,
            "contact_support_index_placements_examined": self.placements_examined,
            "contact_support_index_committed_placements": self.committed_placements,
            "contact_support_index_estimated_scans_avoided": self.estimated_scans_avoided,
        }


class ContactSupportIndex:
    """Per-container top-face index with deterministic XY broad-phase filtering."""

    def __init__(
        self,
        placements: tuple[Placement, ...] | list[Placement] = (),
        *,
        stats: ContactSupportIndexStats | None = None,
    ) -> None:
        self._top_levels: list[float] = []
        self._by_top: dict[float, list[tuple[float, str, Placement]]] = {}
        self._placement_count = 0
        self.stats = stats or ContactSupportIndexStats()
        for placement in sorted(placements, key=lambda value: value.item_id):
            self.add(placement)

    @property
    def placement_count(self) -> int:
        return self._placement_count

    def add(self, placement: Placement) -> None:
        top = placement.z_mm + placement.height_mm
        if top not in self._by_top:
            insort(self._top_levels, top)
            self._by_top[top] = []
        insort(
            self._by_top[top],
            (placement.x_mm, placement.item_id, placement),
        )
        self._placement_count += 1
        self.stats.committed_placements += 1

    def supporters(
        self,
        child: Placement,
        *,
        epsilon_mm: float,
        extra_placements: tuple[Placement, ...] = (),
    ) -> tuple[Placement, ...]:
        """Return exact positive-area contacts after indexed broad phase."""
        if epsilon_mm <= 0:
            raise ValueError("epsilon_mm must be positive")
        self.stats.queries += 1
        self.stats.brute_force_placements += self._placement_count + len(extra_placements)
        minimum = child.z_mm - epsilon_mm
        maximum = child.z_mm + epsilon_mm
        left = bisect_left(self._top_levels, minimum)
        right = bisect_right(self._top_levels, maximum)
        max_child_x = child.x_mm + child.length_mm
        max_child_y = child.y_mm + child.width_mm
        candidates: dict[str, Placement] = {}
        for level in self._top_levels[left:right]:
            entries = self._by_top[level]
            x_stop = bisect_left(entries, (max_child_x, "", child))
            for _, _, supporter in entries[:x_stop]:
                if supporter.item_id == child.item_id:
                    continue
                if supporter.x_mm + supporter.length_mm <= child.x_mm:
                    continue
                if supporter.y_mm >= max_child_y:
                    continue
                if supporter.y_mm + supporter.width_mm <= child.y_mm:
                    continue
                candidates[supporter.item_id] = supporter
        for supporter in extra_placements:
            if (
                supporter.item_id != child.item_id
                and supporter.container_id == child.container_id
                and abs(child.z_mm - (supporter.z_mm + supporter.height_mm)) <= epsilon_mm
                and supporter.x_mm < max_child_x
                and supporter.x_mm + supporter.length_mm > child.x_mm
                and supporter.y_mm < max_child_y
                and supporter.y_mm + supporter.width_mm > child.y_mm
            ):
                candidates[supporter.item_id] = supporter
        ordered = tuple(candidates[item_id] for item_id in sorted(candidates))
        self.stats.placements_examined += len(ordered)
        return tuple(
            supporter for supporter in ordered
            if contact_rectangle(child, supporter) is not None
        )


@dataclass(frozen=True)
class PlacementFeasibilityContext:
    """Optional construction-only lookup context for one container state."""

    contact_support_index: ContactSupportIndex
    projected_placements: tuple[Placement, ...] = ()

    def supporters(
        self, child: Placement, *, epsilon_mm: float,
    ) -> tuple[Placement, ...]:
        return self.contact_support_index.supporters(
            child,
            epsilon_mm=epsilon_mm,
            extra_placements=self.projected_placements,
        )
