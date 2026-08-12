"""Guidance phụ cho construction; không thay feasibility hay objective chính thức."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ...geometry.support import evaluate_support
from ...schemas import Container, Placement


class CandidateState(Protocol):
    container: Container
    placements: list[Placement]
    loaded_weight_kg: float
    loaded_volume_mm3: float


@dataclass(frozen=True)
class SecondaryCandidateScoringPolicy:
    """Đưa KPI phụ sau hai thành phần open/cost của Best Fit hiện hữu."""

    support_threshold: float | None = None
    support_epsilon_mm: float = 1e-4
    policy_id: str = "secondary_utilization_void_support_guidance_v1"

    def score(
        self,
        state: CandidateState,
        candidate: Placement,
        container_rank: int,
        base_score: tuple[float, ...],
    ) -> tuple[float, ...]:
        del container_rank
        container_volume = (
            state.container.length_mm
            * state.container.width_mm
            * state.container.height_mm
        )
        candidate_volume = (
            candidate.length_mm * candidate.width_mm * candidate.height_mm
        )
        volume_utilization = (
            state.loaded_volume_mm3 + candidate_volume
        ) / max(container_volume, 1e-12)
        payload_utilization = (
            state.loaded_weight_kg + candidate.weight_kg
        ) / max(state.container.max_weight_kg, 1e-12)
        concentration = (
            volume_utilization ** 2 + payload_utilization ** 2
        ) / 2.0

        values = [*state.placements, candidate]
        max_x = max(value.x_mm + value.length_mm for value in values)
        max_y = max(value.y_mm + value.width_mm for value in values)
        max_z = max(value.z_mm + value.height_mm for value in values)
        loaded_volume = state.loaded_volume_mm3 + candidate_volume
        internal_void_ratio = max(
            max_x * max_y * max_z - loaded_volume, 0.0
        ) / max(container_volume, 1e-12)

        minimum_support_margin = 0.0
        if self.support_threshold is not None:
            margins = [
                evaluate_support(
                    placement, values, epsilon_mm=self.support_epsilon_mm,
                ).exact_support_ratio - self.support_threshold
                for placement in values
            ]
            minimum_support_margin = min(margins, default=0.0)

        prefix = base_score[:2]
        suffix = base_score[2:]
        return (
            *prefix,
            -float(concentration),
            float(internal_void_ratio),
            -float(minimum_support_margin),
            *suffix,
        )

    def metadata(self) -> dict[str, object]:
        return {
            "candidate_secondary_scoring_policy": self.policy_id,
            "candidate_secondary_support_component_active": (
                self.support_threshold is not None
            ),
        }


def configured_secondary_candidate_policy(
    settings: dict,
    *,
    exact_support_active: bool,
) -> SecondaryCandidateScoringPolicy | None:
    raw = settings.get("container_search", {}).get("secondary_search_score", {})
    if not isinstance(raw, dict) or not bool(raw.get("enabled", False)):
        return None
    support = settings.get("support", {})
    return SecondaryCandidateScoringPolicy(
        support_threshold=(
            float(support.get("threshold", 0.8))
            if exact_support_active else None
        ),
        support_epsilon_mm=float(support.get("epsilon_mm", 1e-4)),
    )
