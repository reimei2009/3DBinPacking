"""Small-instance Level 3 MILP reference with horizontal orientation binaries."""

from __future__ import annotations

from math import ceil
from typing import Any

import numpy as np

from ..common.constants import DIRECTIONS, Direction
from ..common.fixed_orientation_milp import (
    ConstraintBuilder,
    FixedOrientationAssembly,
    MilpProblem,
    add_capacity_strengthening_cuts,
    finish_problem,
)
from ..level_02.milp_model import validate_support_settings
from .model_indices import Level03ModelIndices
from ...schemas import Container, Item


def _orientation_dimensions(item: Item) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    return (
        (item.length_mm, item.width_mm, item.height_mm),
        (item.width_mm, item.length_mm, item.height_mm),
    )


def build_level3_model(
    items: list[Item], containers: list[Container], support_settings: dict[str, Any],
) -> MilpProblem:
    """Build exact reference MILP for `XYZ`/`YXZ` plus Level 2 support grid.

    The model is deliberately intended for small instances only. Exact
    rectangle-union support validation remains authoritative after decoding.
    """
    n, m = len(items), len(containers)
    grid_x, grid_y, threshold, minimum_points = validate_support_settings(support_settings)
    indices = Level03ModelIndices(n, m, grid_x, grid_y)
    priority = 1.0 + sum(container.cost for container in containers)
    objective = np.zeros(indices.n_variables)
    integrality = np.zeros(indices.n_variables, dtype=np.uint8)
    lower = np.zeros(indices.n_variables)
    upper = np.full(indices.n_variables, np.inf)
    max_x = max(container.length_mm for container in containers)
    max_y = max(container.width_mm for container in containers)
    max_z = max(container.height_mm for container in containers)
    builder = ConstraintBuilder(indices.n_variables)

    for k, container in enumerate(containers):
        objective[indices.u(k)] = priority + container.cost
        integrality[indices.u(k)] = 1
        upper[indices.u(k)] = container.availability
    for i, item in enumerate(items):
        upper[indices.x(i)] = max_x
        upper[indices.y(i)] = max_y
        upper[indices.z(i)] = max_z
        for code in (0, 1):
            column = indices.orientation(i, code)
            integrality[column] = 1
            upper[column] = 0 if code == 1 and item.length_mm == item.width_mm else 1
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
    for i in range(n):
        for k in range(m):
            for column in (indices.floor(i, k),):
                integrality[column] = 1
                upper[column] = 1
        for j in range(n):
            if i == j:
                continue
            for k in range(m):
                center = indices.center_support(i, j, k)
                integrality[center] = 1
                upper[center] = 1
                for p in range(grid_x):
                    for q in range(grid_y):
                        support = indices.support_point(i, j, k, p, q)
                        integrality[support] = 1
                        upper[support] = 1

    # R1/R2 plus exactly one allowed horizontal orientation.
    for i in range(n):
        builder.add({indices.a(i, k): 1 for k in range(m)}, 1, 1)
        builder.add({indices.orientation(i, code): 1 for code in (0, 1)}, 1, 1)
        for k in range(m):
            builder.add({indices.a(i, k): 1, indices.u(k): -1}, upper=0)

    # Orientation-dependent container boundaries and payload.
    for i, item in enumerate(items):
        dimensions = _orientation_dimensions(item)
        for k, container in enumerate(containers):
            for coordinate, limit, axis, maximum in (
                (indices.x(i), container.length_mm, 0, max_x),
                (indices.y(i), container.width_mm, 1, max_y),
                (indices.z(i), container.height_mm, 2, max_z),
            ):
                coefficients = {coordinate: 1, indices.a(i, k): maximum}
                coefficients.update({indices.orientation(i, code): dimensions[code][axis] for code in (0, 1)})
                builder.add(coefficients, upper=limit + maximum)
    for k, container in enumerate(containers):
        coefficients = {indices.a(i, k): item.weight_kg for i, item in enumerate(items)}
        coefficients[indices.u(k)] = -container.max_weight_kg
        builder.add(coefficients, upper=0)

    # Six-direction non-overlap with orientation-dependent extent.
    for i, item_i in enumerate(items):
        dimensions_i = _orientation_dimensions(item_i)
        for j in range(i + 1, n):
            item_j = items[j]
            dimensions_j = _orientation_dimensions(item_j)
            for k in range(m):
                deltas = [indices.delta(i, j, k, direction) for direction in DIRECTIONS]
                for delta in deltas:
                    builder.add({delta: 1, indices.a(i, k): -1}, upper=0)
                    builder.add({delta: 1, indices.a(j, k): -1}, upper=0)
                activation = {delta: 1 for delta in deltas}
                activation.update({indices.a(i, k): -1, indices.a(j, k): -1})
                builder.add(activation, lower=-1)
                _add_separation(builder, indices, i, j, k, Direction.LEFT, indices.x(i), indices.x(j), dimensions_i, 0, max_x)
                _add_separation(builder, indices, i, j, k, Direction.RIGHT, indices.x(j), indices.x(i), dimensions_j, 0, max_x)
                _add_separation(builder, indices, i, j, k, Direction.FRONT, indices.y(i), indices.y(j), dimensions_i, 1, max_y)
                _add_separation(builder, indices, i, j, k, Direction.BACK, indices.y(j), indices.y(i), dimensions_j, 1, max_y)
                _add_separation(builder, indices, i, j, k, Direction.BELOW, indices.z(i), indices.z(j), dimensions_i, 2, max_z)
                _add_separation(builder, indices, i, j, k, Direction.ABOVE, indices.z(j), indices.z(i), dimensions_j, 2, max_z)

    # Level 2 floor/support grid with dimensions expressed linearly in r[i,o].
    for i in range(n):
        for k in range(m):
            floor = indices.floor(i, k)
            builder.add({floor: 1, indices.a(i, k): -1}, upper=0)
            builder.add({indices.z(i): 1, floor: max_z}, upper=max_z)
    for i, item_i in enumerate(items):
        dimensions_i = _orientation_dimensions(item_i)
        for j, item_j in enumerate(items):
            if i == j:
                continue
            dimensions_j = _orientation_dimensions(item_j)
            for k in range(m):
                center = indices.center_support(i, j, k)
                _link_support_binary(builder, indices, i, j, k, center)
                _add_contact(builder, indices, i, j, center, item_j.height_mm, max_z)
                _add_oriented_point_inside(builder, indices, i, j, center, 0.5, 0.5, dimensions_i, dimensions_j, max_x, max_y)
                for p in range(grid_x):
                    for q in range(grid_y):
                        support = indices.support_point(i, j, k, p, q)
                        _link_support_binary(builder, indices, i, j, k, support)
                        _add_contact(builder, indices, i, j, support, item_j.height_mm, max_z)
                        _add_oriented_point_inside(
                            builder, indices, i, j, support,
                            (p + 0.5) / grid_x, (q + 0.5) / grid_y,
                            dimensions_i, dimensions_j, max_x, max_y,
                        )
    grid_size = indices.grid_size
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
            coverage.update({floor: grid_size, indices.a(i, k): -minimum_points})
            builder.add(coverage, lower=0)
            center_coverage = {column: 1 for column in center_columns}
            center_coverage.update({floor: 1, indices.a(i, k): -1})
            builder.add(center_coverage, lower=0)
            builder.add({column: 1 for column in center_columns}, upper=1)
            no_floor_points = {column: 1 for column in support_columns}
            no_floor_points[floor] = grid_size
            builder.add(no_floor_points, upper=grid_size)
            no_floor_center = {column: 1 for column in center_columns}
            no_floor_center[floor] = 1
            builder.add(no_floor_center, upper=1)

    assembly = FixedOrientationAssembly(objective, integrality, lower, upper, builder, max_x, max_y, max_z, priority)
    strengthening_metadata = add_capacity_strengthening_cuts(assembly, items, containers, indices)
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
            "orientation_variable_count": indices.orientation_count,
            "orientation_codes": ["XYZ", "YXZ"],
            "orientation_reference_max_items": 5,
            **strengthening_metadata,
        },
    )


def _add_separation(builder, indices, i, j, k, direction, left, right, dimensions, axis, maximum) -> None:
    coefficients = {left: 1, right: -1, indices.delta(i, j, k, direction): maximum}
    coefficients.update({indices.orientation(i, code): dimensions[code][axis] for code in (0, 1)})
    builder.add(coefficients, upper=maximum)


def _link_support_binary(builder, indices, i, j, k, binary) -> None:
    builder.add({binary: 1, indices.a(i, k): -1}, upper=0)
    builder.add({binary: 1, indices.a(j, k): -1}, upper=0)


def _add_contact(builder, indices, i, j, binary, height_j, max_z) -> None:
    builder.add({indices.z(i): 1, indices.z(j): -1, binary: max_z}, upper=max_z + height_j)
    builder.add({indices.z(i): 1, indices.z(j): -1, binary: -max_z}, lower=height_j - max_z)


def _add_oriented_point_inside(
    builder, indices, i, j, binary, x_fraction, y_fraction,
    dimensions_i, dimensions_j, max_x, max_y,
) -> None:
    # x_i + fraction*l_i lies inside [x_j, x_j + l_j] when binary is active.
    lower = {indices.x(i): 1, indices.x(j): -1, binary: -max_x}
    lower.update({indices.orientation(i, code): x_fraction * dimensions_i[code][0] for code in (0, 1)})
    builder.add(lower, lower=-max_x)
    upper = {indices.x(i): 1, indices.x(j): -1, binary: max_x}
    upper.update({
        indices.orientation(i, code): x_fraction * dimensions_i[code][0]
        for code in (0, 1)
    })
    for code in (0, 1):
        upper[indices.orientation(j, code)] = upper.get(indices.orientation(j, code), 0.0) - dimensions_j[code][0]
    builder.add(upper, upper=max_x)
    lower_y = {indices.y(i): 1, indices.y(j): -1, binary: -max_y}
    lower_y.update({indices.orientation(i, code): y_fraction * dimensions_i[code][1] for code in (0, 1)})
    builder.add(lower_y, lower=-max_y)
    upper_y = {indices.y(i): 1, indices.y(j): -1, binary: max_y}
    upper_y.update({
        indices.orientation(i, code): y_fraction * dimensions_i[code][1]
        for code in (0, 1)
    })
    for code in (0, 1):
        upper_y[indices.orientation(j, code)] = upper_y.get(indices.orientation(j, code), 0.0) - dimensions_j[code][1]
    builder.add(upper_y, upper=max_y)
