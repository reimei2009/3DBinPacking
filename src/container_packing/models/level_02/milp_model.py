"""Level 2 MILP: fixed orientation plus geometric floor/support constraints."""

from __future__ import annotations

from math import ceil
from typing import Any

from ..common.fixed_orientation_milp import (
    MilpProblem,
    add_capacity_strengthening_cuts,
    build_fixed_orientation_assembly,
    finish_problem,
)
from .model_indices import Level02ModelIndices
from ...schemas import Container, Item


def validate_support_settings(settings: dict[str, Any]) -> tuple[int, int, float, int]:
    grid_x = int(settings.get("grid_x", 4))
    grid_y = int(settings.get("grid_y", 4))
    threshold = float(settings.get("threshold", 0.8))
    if grid_x <= 0 or grid_y <= 0:
        raise ValueError("support.grid_x and support.grid_y must be positive")
    if not 0 < threshold <= 1:
        raise ValueError("support.threshold must be in (0, 1]")
    return grid_x, grid_y, threshold, ceil(threshold * grid_x * grid_y)


def build_level2_model(
    items: list[Item], containers: list[Container], support_settings: dict[str, Any],
) -> MilpProblem:
    """Compose Level 1 R1-R9 with floor, grid support and center-support constraints."""
    n, m = len(items), len(containers)
    grid_x, grid_y, threshold, minimum_points = validate_support_settings(support_settings)
    indices = Level02ModelIndices(n, m, grid_x, grid_y)
    assembly = build_fixed_orientation_assembly(items, containers, indices, indices.n_variables)
    strengthening_metadata = add_capacity_strengthening_cuts(assembly, items, containers, indices)
    builder = assembly.builder
    grid_size = indices.grid_size

    for i in range(n):
        for k in range(m):
            floor = indices.floor(i, k)
            assembly.integrality[floor] = 1
            assembly.upper[floor] = 1
            builder.add({floor: 1, indices.a(i, k): -1}, upper=0)
            builder.add({indices.z(i): 1, floor: assembly.max_z}, upper=assembly.max_z)

    for i, item_i in enumerate(items):
        for j, item_j in enumerate(items):
            if i == j:
                continue
            for k in range(m):
                center = indices.center_support(i, j, k)
                assembly.integrality[center] = 1
                assembly.upper[center] = 1
                builder.add({center: 1, indices.a(i, k): -1}, upper=0)
                builder.add({center: 1, indices.a(j, k): -1}, upper=0)
                _add_contact(builder, indices, i, j, center, item_j.height_mm, assembly.max_z)
                _add_point_inside(
                    builder, indices, i, j, center,
                    0.5 * item_i.length_mm, 0.5 * item_i.width_mm,
                    item_j.length_mm, item_j.width_mm, assembly.max_x, assembly.max_y,
                )
                for p in range(grid_x):
                    offset_x = ((p + 0.5) / grid_x) * item_i.length_mm
                    for q in range(grid_y):
                        support = indices.support_point(i, j, k, p, q)
                        assembly.integrality[support] = 1
                        assembly.upper[support] = 1
                        builder.add({support: 1, indices.a(i, k): -1}, upper=0)
                        builder.add({support: 1, indices.a(j, k): -1}, upper=0)
                        _add_contact(builder, indices, i, j, support, item_j.height_mm, assembly.max_z)
                        _add_point_inside(
                            builder, indices, i, j, support,
                            offset_x, ((q + 0.5) / grid_y) * item_i.width_mm,
                            item_j.length_mm, item_j.width_mm, assembly.max_x, assembly.max_y,
                        )

    for i in range(n):
        for k in range(m):
            floor = indices.floor(i, k)
            support_columns = [
                indices.support_point(i, j, k, p, q)
                for j in range(n) if j != i for p in range(grid_x) for q in range(grid_y)
            ]
            center_columns = [indices.center_support(i, j, k) for j in range(n) if j != i]
            for p in range(grid_x):
                for q in range(grid_y):
                    builder.add({indices.support_point(i, j, k, p, q): 1 for j in range(n) if j != i}, upper=1)
            coverage = {column: 1 for column in support_columns}
            coverage[floor] = grid_size
            coverage[indices.a(i, k)] = -minimum_points
            builder.add(coverage, lower=0)
            center_coverage = {column: 1 for column in center_columns}
            center_coverage[floor] = 1
            center_coverage[indices.a(i, k)] = -1
            builder.add(center_coverage, lower=0)
            builder.add({column: 1 for column in center_columns}, upper=1)
            no_floor_points = {column: 1 for column in support_columns}
            no_floor_points[floor] = grid_size
            builder.add(no_floor_points, upper=grid_size)
            no_floor_center = {column: 1 for column in center_columns}
            no_floor_center[floor] = 1
            builder.add(no_floor_center, upper=1)

    return finish_problem(
        assembly,
        indices,
        metadata={
            "n_items": n, "n_containers": m, "n_pairs": indices.n_pairs,
            "support_grid_x": grid_x, "support_grid_y": grid_y,
            "support_grid_size": grid_size, "support_threshold": threshold,
            "minimum_supported_points": minimum_points,
            "floor_variable_count": indices.floor_count,
            "support_point_variable_count": indices.support_point_count,
            "center_support_variable_count": indices.center_support_count,
            **strengthening_metadata,
        },
    )


def _add_contact(builder, indices, i: int, j: int, binary: int, height_j: float, max_z: float) -> None:
    builder.add({indices.z(i): 1, indices.z(j): -1, binary: max_z}, upper=max_z + height_j)
    builder.add({indices.z(i): 1, indices.z(j): -1, binary: -max_z}, lower=height_j - max_z)


def _add_point_inside(
    builder, indices, i: int, j: int, binary: int,
    offset_x: float, offset_y: float, length_j: float, width_j: float, max_x: float, max_y: float,
) -> None:
    builder.add({indices.x(i): 1, indices.x(j): -1, binary: -max_x}, lower=-max_x - offset_x)
    builder.add({indices.x(i): 1, indices.x(j): -1, binary: max_x}, upper=length_j + max_x - offset_x)
    builder.add({indices.y(i): 1, indices.y(j): -1, binary: -max_y}, lower=-max_y - offset_y)
    builder.add({indices.y(i): 1, indices.y(j): -1, binary: max_y}, upper=width_j + max_y - offset_y)
