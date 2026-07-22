"""Composable placement-feasibility policies for reusable packing engines."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from ..geometry.support import evaluate_support
from ..schemas import Container, Placement


class PlacementFeasibilityPolicy(Protocol):
    policy_id: str

    def allows(
        self,
        container: Container,
        existing: list[Placement],
        candidate: Placement,
        *,
        loaded_weight_kg: float,
        tolerance: float,
    ) -> bool: ...

    def metadata(self) -> dict[str, Any]: ...


def placements_overlap(left: Placement, right: Placement, tolerance: float) -> bool:
    return not (
        left.x_mm + left.length_mm <= right.x_mm + tolerance
        or right.x_mm + right.length_mm <= left.x_mm + tolerance
        or left.y_mm + left.width_mm <= right.y_mm + tolerance
        or right.y_mm + right.width_mm <= left.y_mm + tolerance
        or left.z_mm + left.height_mm <= right.z_mm + tolerance
        or right.z_mm + right.height_mm <= left.z_mm + tolerance
    )


@dataclass
class FixedOrientationFeasibilityPolicy:
    policy_id: str = "fixed_orientation_geometry_payload"
    candidates_evaluated: int = 0
    geometry_rejected_candidates: int = 0

    def allows(
        self,
        container: Container,
        existing: list[Placement],
        candidate: Placement,
        *,
        loaded_weight_kg: float,
        tolerance: float,
    ) -> bool:
        self.candidates_evaluated += 1
        valid = not (
            loaded_weight_kg + candidate.weight_kg > container.max_weight_kg + tolerance
            or candidate.x_mm < -tolerance
            or candidate.y_mm < -tolerance
            or candidate.z_mm < -tolerance
            or candidate.x_mm + candidate.length_mm > container.length_mm + tolerance
            or candidate.y_mm + candidate.width_mm > container.width_mm + tolerance
            or candidate.z_mm + candidate.height_mm > container.height_mm + tolerance
            or any(placements_overlap(candidate, placed, tolerance) for placed in existing)
        )
        if not valid:
            self.geometry_rejected_candidates += 1
        return valid

    def metadata(self) -> dict[str, Any]:
        return {
            "feasibility_policy": self.policy_id,
            "candidate_feasibility_checks": self.candidates_evaluated,
            "geometry_rejected_candidates": self.geometry_rejected_candidates,
        }


@dataclass
class ExactSupportFeasibilityPolicy:
    threshold: float
    epsilon_mm: float
    base: PlacementFeasibilityPolicy = field(default_factory=FixedOrientationFeasibilityPolicy)
    policy_id: str = "fixed_orientation_geometry_payload_exact_support"
    support_rejected_candidates: int = 0
    support_valid_candidates: int = 0

    def __post_init__(self) -> None:
        if not 0 < self.threshold <= 1:
            raise ValueError("support threshold must be in (0, 1]")
        if self.epsilon_mm <= 0:
            raise ValueError("support epsilon must be positive")

    def allows(
        self,
        container: Container,
        existing: list[Placement],
        candidate: Placement,
        *,
        loaded_weight_kg: float,
        tolerance: float,
    ) -> bool:
        if not self.base.allows(
            container, existing, candidate,
            loaded_weight_kg=loaded_weight_kg, tolerance=tolerance,
        ):
            return False
        support = evaluate_support(candidate, existing, epsilon_mm=self.epsilon_mm)
        valid = support.exact_support_ratio + 1e-12 >= self.threshold and support.center_supported
        if valid:
            self.support_valid_candidates += 1
        else:
            self.support_rejected_candidates += 1
        return valid

    def metadata(self) -> dict[str, Any]:
        return {
            **self.base.metadata(),
            "feasibility_policy": self.policy_id,
            "heuristic_support_threshold": self.threshold,
            "heuristic_support_epsilon_mm": self.epsilon_mm,
            "support_rejected_candidates": self.support_rejected_candidates,
            "support_valid_candidates": self.support_valid_candidates,
        }
