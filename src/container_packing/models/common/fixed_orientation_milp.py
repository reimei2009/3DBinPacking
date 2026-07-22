"""Shared sparse MILP core for fixed-orientation rectangular packing."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from typing import Any, Protocol

import numpy as np
from scipy.optimize import Bounds, LinearConstraint
from scipy.sparse import coo_matrix, csr_matrix

from ...schemas import Container, Item
from .constants import DIRECTIONS, Direction


class FixedOrientationIndices(Protocol):
    n_pairs: int

    def u(self, k: int) -> int: ...
    def a(self, i: int, k: int) -> int: ...
    def x(self, i: int) -> int: ...
    def y(self, i: int) -> int: ...
    def z(self, i: int) -> int: ...
    def delta(self, i: int, j: int, k: int, direction: Direction | str) -> int: ...


@dataclass(frozen=True)
class MilpProblem:
    objective: np.ndarray
    integrality: np.ndarray
    bounds: Bounds
    constraints: LinearConstraint
    indices: Any
    metadata: dict[str, Any]


class ConstraintBuilder:
    """Incrementally construct one sparse linear-constraint matrix."""

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
                self.rows.append(row)
                self.columns.append(column)
                self.values.append(float(value))
        self.lower.append(float(lower))
        self.upper.append(float(upper))

    def finish(self) -> tuple[csr_matrix, np.ndarray, np.ndarray]:
        matrix = coo_matrix(
            (self.values, (self.rows, self.columns)),
            shape=(len(self.lower), self.n_variables), dtype=float,
        ).tocsr()
        return matrix, np.asarray(self.lower), np.asarray(self.upper)


@dataclass
class FixedOrientationAssembly:
    objective: np.ndarray
    integrality: np.ndarray
    lower: np.ndarray
    upper: np.ndarray
    builder: ConstraintBuilder
    max_x: float
    max_y: float
    max_z: float
    priority: float


def add_capacity_strengthening_cuts(
    assembly: FixedOrientationAssembly,
    items: list[Item],
    containers: list[Container],
    indices: FixedOrientationIndices,
) -> dict[str, Any]:
    """Add redundant capacity inequalities without changing the feasible set.

    Boundary and non-overlap constraints already imply volume feasibility. The
    explicit normalized inequalities expose that implication to the MILP
    relaxation and make container activation easier for the solver to reason
    about. Payload has an assignment-level constraint already; its global cut
    is included for the same relaxation-strengthening purpose.
    """
    item_volumes = [item.volume_m3 for item in items]
    container_volumes = [
        container.length_mm * container.width_mm * container.height_mm / 1_000_000_000.0
        for container in containers
    ]

    for k, capacity in enumerate(container_volumes):
        coefficients = {
            indices.a(i, k): volume / capacity
            for i, volume in enumerate(item_volumes)
        }
        coefficients[indices.u(k)] = -1.0
        assembly.builder.add(coefficients, upper=0.0)

    total_volume = sum(item_volumes)
    total_weight = sum(item.weight_kg for item in items)
    max_volume = max(container_volumes)
    max_payload = max(container.max_weight_kg for container in containers)
    assembly.builder.add(
        {indices.u(k): capacity / max_volume for k, capacity in enumerate(container_volumes)},
        lower=total_volume / max_volume,
    )
    assembly.builder.add(
        {
            indices.u(k): container.max_weight_kg / max_payload
            for k, container in enumerate(containers)
        },
        lower=total_weight / max_payload,
    )
    volume_lower_bound = ceil(total_volume / max_volume - 1e-12)
    payload_lower_bound = ceil(total_weight / max_payload - 1e-12)
    minimum_containers = max(1, volume_lower_bound, payload_lower_bound)
    assembly.builder.add(
        {indices.u(k): 1.0 for k in range(len(containers))},
        lower=minimum_containers,
    )
    return {
        "capacity_strengthening_enabled": True,
        "capacity_strengthening_cut_count": len(containers) + 3,
        "container_count_lower_bound": minimum_containers,
        "volume_container_count_lower_bound": volume_lower_bound,
        "payload_container_count_lower_bound": payload_lower_bound,
    }


def build_fixed_orientation_assembly(
    items: list[Item], containers: list[Container], indices: FixedOrientationIndices, n_variables: int,
) -> FixedOrientationAssembly:
    """Add the exact Level-1 objective and R1-R9 to an extensible vector."""
    n, m = len(items), len(containers)
    objective = np.zeros(n_variables)
    priority = 1.0 + sum(container.cost for container in containers)
    for k, container in enumerate(containers):
        objective[indices.u(k)] = priority + container.cost

    integrality = np.zeros(n_variables, dtype=np.uint8)
    lower = np.zeros(n_variables)
    upper = np.full(n_variables, np.inf)
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
            integrality[indices.a(i, k)] = 1
            upper[indices.a(i, k)] = 1
    for i in range(n):
        for j in range(i + 1, n):
            for k in range(m):
                for direction in DIRECTIONS:
                    column = indices.delta(i, j, k, direction)
                    integrality[column] = 1
                    upper[column] = 1

    builder = ConstraintBuilder(n_variables)
    for i in range(n):
        builder.add({indices.a(i, k): 1 for k in range(m)}, 1, 1)
    for i in range(n):
        for k in range(m):
            builder.add({indices.a(i, k): 1, indices.u(k): -1}, upper=0)
    for i, item in enumerate(items):
        for k, container in enumerate(containers):
            builder.add({indices.x(i): 1, indices.a(i, k): max_x}, upper=container.length_mm + max_x - item.length_mm)
            builder.add({indices.y(i): 1, indices.a(i, k): max_y}, upper=container.width_mm + max_y - item.width_mm)
            builder.add({indices.z(i): 1, indices.a(i, k): max_z}, upper=container.height_mm + max_z - item.height_mm)
    for k, container in enumerate(containers):
        coefficients = {indices.a(i, k): item.weight_kg for i, item in enumerate(items)}
        coefficients[indices.u(k)] = -container.max_weight_kg
        builder.add(coefficients, upper=0)
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
    return FixedOrientationAssembly(
        objective, integrality, lower, upper, builder, max_x, max_y, max_z, priority,
    )


def finish_problem(
    assembly: FixedOrientationAssembly, indices: FixedOrientationIndices, *, metadata: dict[str, Any],
) -> MilpProblem:
    matrix, constraint_lower, constraint_upper = assembly.builder.finish()
    return MilpProblem(
        objective=assembly.objective,
        integrality=assembly.integrality,
        bounds=Bounds(assembly.lower, assembly.upper),
        constraints=LinearConstraint(matrix, constraint_lower, constraint_upper),
        indices=indices,
        metadata={
            **metadata,
            "n_variables": len(assembly.objective),
            "n_constraints": matrix.shape[0],
            "constraint_nnz": matrix.nnz,
            "big_m": {"x": assembly.max_x, "y": assembly.max_y, "z": assembly.max_z},
            "objective_priority_constant": assembly.priority,
        },
    )
