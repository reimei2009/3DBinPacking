"""Sparse construction of the exact Level 1 MILP formulation."""

from __future__ import annotations

from ..common.fixed_orientation_milp import (
    MilpProblem,
    build_fixed_orientation_assembly,
    finish_problem,
)
from .model_indices import ModelIndices
from ...schemas import Container, Item


def build_level1_model(items: list[Item], containers: list[Container]) -> MilpProblem:
    """Build the no-rotation/no-support Level 1 model using shared sparse primitives."""
    indices = ModelIndices(len(items), len(containers))
    assembly = build_fixed_orientation_assembly(items, containers, indices, indices.n_variables)
    return finish_problem(
        assembly,
        indices,
        metadata={"n_items": len(items), "n_containers": len(containers), "n_pairs": indices.n_pairs},
    )


__all__ = ["MilpProblem", "build_level1_model"]
