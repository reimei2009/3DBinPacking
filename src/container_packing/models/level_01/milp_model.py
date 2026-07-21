"""Sparse construction of the exact Level 1 MILP formulation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import Bounds, LinearConstraint
from scipy.sparse import coo_matrix, csr_matrix

from .constants import DIRECTIONS, Direction
from .model_indices import ModelIndices
from ...schemas import Container, Item


@dataclass(frozen=True)
class MilpProblem:
    objective: np.ndarray
    integrality: np.ndarray
    bounds: Bounds
    constraints: LinearConstraint
    indices: ModelIndices
    metadata: dict[str, Any]


class _ConstraintBuilder:
    def __init__(self, n_variables: int) -> None:
        self.n_variables = n_variables
        self.rows: list[int] = []
        self.columns: list[int] = []
        self.values: list[float] = []
        self.lower: list[float] = []
        self.upper: list[float] = []

    def add(self, coefficients: dict[int, float], lower: float = -np.inf, upper: float = np.inf) -> None:
        row = len(self.lower)
        for column, value in coefficients.items():
            if value:
                self.rows.append(row); self.columns.append(column); self.values.append(float(value))
        self.lower.append(float(lower)); self.upper.append(float(upper))

    def finish(self) -> tuple[csr_matrix, np.ndarray, np.ndarray]:
        matrix = coo_matrix(
            (self.values, (self.rows, self.columns)),
            shape=(len(self.lower), self.n_variables), dtype=float,
        ).tocsr()
        return matrix, np.asarray(self.lower), np.asarray(self.upper)


def build_level1_model(items: list[Item], containers: list[Container]) -> MilpProblem:
    """Build the no-rotation/no-support Level 1 model using sparse constraints."""
    n, m = len(items), len(containers)
    indices = ModelIndices(n, m)
    size = indices.n_variables
    objective = np.zeros(size)
    priority = 1.0 + sum(container.cost for container in containers)
    for k, container in enumerate(containers):
        objective[indices.u(k)] = priority + container.cost

    integrality = np.zeros(size, dtype=np.uint8)
    lower = np.zeros(size)
    upper = np.full(size, np.inf)
    max_x = max(container.length_mm for container in containers)
    max_y = max(container.width_mm for container in containers)
    max_z = max(container.height_mm for container in containers)
    for k, container in enumerate(containers):
        integrality[indices.u(k)] = 1
        upper[indices.u(k)] = container.availability
    for i in range(n):
        upper[indices.x(i)] = max_x
        upper[indices.y(i)] = max_y
        upper[indices.z(i)] = max_z
        for k in range(m):
            integrality[indices.a(i, k)] = 1; upper[indices.a(i, k)] = 1
    for i in range(n):
        for j in range(i + 1, n):
            for k in range(m):
                for direction in DIRECTIONS:
                    column = indices.delta(i, j, k, direction)
                    integrality[column] = 1; upper[column] = 1

    builder = _ConstraintBuilder(size)
    # R1: exact assignment.
    for i in range(n):
        builder.add({indices.a(i, k): 1 for k in range(m)}, 1, 1)
    # R2: assignment implies container use.
    for i in range(n):
        for k in range(m):
            builder.add({indices.a(i, k): 1, indices.u(k): -1}, upper=0)
    # R3-R5: fixed-orientation container boundaries.
    for i, item in enumerate(items):
        for k, container in enumerate(containers):
            builder.add({indices.x(i): 1, indices.a(i, k): max_x}, upper=container.length_mm + max_x - item.length_mm)
            builder.add({indices.y(i): 1, indices.a(i, k): max_y}, upper=container.width_mm + max_y - item.width_mm)
            builder.add({indices.z(i): 1, indices.a(i, k): max_z}, upper=container.height_mm + max_z - item.height_mm)
    # R6: payload capacity.
    for k, container in enumerate(containers):
        coefficients = {indices.a(i, k): item.weight_kg for i, item in enumerate(items)}
        coefficients[indices.u(k)] = -container.max_weight_kg
        builder.add(coefficients, upper=0)
    # R7-R9: activated disjunction and pairwise separation.
    for i, item_i in enumerate(items):
        for j in range(i + 1, n):
            item_j = items[j]
            for k in range(m):
                deltas = [indices.delta(i, j, k, d) for d in DIRECTIONS]
                for delta in deltas:
                    builder.add({delta: 1, indices.a(i, k): -1}, upper=0)
                    builder.add({delta: 1, indices.a(j, k): -1}, upper=0)
                activation = {delta: 1 for delta in deltas}
                activation[indices.a(i, k)] = -1
                activation[indices.a(j, k)] = -1
                builder.add(activation, lower=-1)
                builder.add({indices.x(i): 1, indices.x(j): -1, indices.delta(i, j, k, Direction.LEFT): max_x}, upper=max_x - item_i.length_mm)
                builder.add({indices.x(j): 1, indices.x(i): -1, indices.delta(i, j, k, Direction.RIGHT): max_x}, upper=max_x - item_j.length_mm)
                builder.add({indices.y(i): 1, indices.y(j): -1, indices.delta(i, j, k, Direction.FRONT): max_y}, upper=max_y - item_i.width_mm)
                builder.add({indices.y(j): 1, indices.y(i): -1, indices.delta(i, j, k, Direction.BACK): max_y}, upper=max_y - item_j.width_mm)
                builder.add({indices.z(i): 1, indices.z(j): -1, indices.delta(i, j, k, Direction.BELOW): max_z}, upper=max_z - item_i.height_mm)
                builder.add({indices.z(j): 1, indices.z(i): -1, indices.delta(i, j, k, Direction.ABOVE): max_z}, upper=max_z - item_j.height_mm)

    matrix, constraint_lower, constraint_upper = builder.finish()
    metadata = {
        "n_items": n, "n_containers": m, "n_pairs": indices.n_pairs,
        "n_variables": size, "n_constraints": matrix.shape[0],
        "constraint_nnz": matrix.nnz,
        "big_m": {"x": max_x, "y": max_y, "z": max_z},
        "objective_priority_constant": priority,
    }
    return MilpProblem(
        objective=objective, integrality=integrality, bounds=Bounds(lower, upper),
        constraints=LinearConstraint(matrix, constraint_lower, constraint_upper),
        indices=indices, metadata=metadata,
    )
