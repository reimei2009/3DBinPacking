"""Typed domain objects used across loading, solving, and reporting."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from scipy.optimize import OptimizeResult


@dataclass(frozen=True)
class Item:
    item_id: str
    length_mm: float
    width_mm: float
    height_mm: float
    weight_kg: float
    level1_order: int = 0
    source: dict[str, Any] = field(default_factory=dict, compare=False)

    @property
    def volume_m3(self) -> float:
        return self.length_mm * self.width_mm * self.height_mm / 1_000_000_000.0


@dataclass(frozen=True)
class Container:
    container_id: str
    length_mm: float
    width_mm: float
    height_mm: float
    max_weight_kg: float
    cost: float
    availability: int = 1
    volume_m3: float = 0.0
    source: dict[str, Any] = field(default_factory=dict, compare=False)


@dataclass(frozen=True)
class Placement:
    item_id: str
    container_id: str
    x_mm: float
    y_mm: float
    z_mm: float
    length_mm: float
    width_mm: float
    height_mm: float
    weight_kg: float

    @property
    def volume_m3(self) -> float:
        return self.length_mm * self.width_mm * self.height_mm / 1_000_000_000.0


@dataclass(frozen=True)
class ContainerUsage:
    container_id: str
    used: bool
    item_count: int
    loaded_weight_kg: float
    loaded_volume_m3: float


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    item_ids: tuple[str, ...] = ()
    container_id: str | None = None


@dataclass
class ValidationResult:
    valid: bool
    issues: list[ValidationIssue]


@dataclass
class SolveResult:
    status: str
    message: str
    objective_value: float | None
    vector: Any | None
    raw_result: OptimizeResult


@dataclass
class RunResult:
    solve: SolveResult
    placements: list[Placement]
    validation: ValidationResult | None
    metadata: dict[str, Any]
