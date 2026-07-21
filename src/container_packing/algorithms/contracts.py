"""Canonical outcome returned by exact and heuristic packing algorithms."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..schemas import Placement, SolveResult


@dataclass
class AlgorithmOutcome:
    solve: SolveResult
    placements: list[Placement]
    backend: str
    metadata: dict[str, Any] = field(default_factory=dict)
