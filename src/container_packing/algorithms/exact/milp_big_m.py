"""SciPy/HiGHS solver adapter and Level 1 solution extraction."""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.optimize import milp

from ..contracts import AlgorithmOutcome
from ...models.level_01.milp_model import MilpProblem, build_level1_model
from ...schemas import Container, Item, Placement, SolveResult


def solve_milp(problem: MilpProblem, settings: dict[str, Any] | None = None) -> SolveResult:
    settings = settings or {}
    options = {
        "time_limit": float(settings.get("time_limit_seconds", 600)),
        "mip_rel_gap": float(settings.get("mip_rel_gap", 0.0)),
        "presolve": bool(settings.get("presolve", True)),
        "disp": bool(settings.get("display", False)),
    }
    raw = milp(
        c=problem.objective, integrality=problem.integrality, bounds=problem.bounds,
        constraints=problem.constraints, options=options,
    )
    vector = raw.x if getattr(raw, "x", None) is not None and np.all(np.isfinite(raw.x)) else None
    if raw.status == 0 and raw.success and vector is not None:
        status = "OPTIMAL"
    elif raw.status == 1 and vector is not None:
        status = "FEASIBLE_TIME_LIMIT"
    elif raw.status == 2:
        status = "INFEASIBLE"
    elif raw.status == 3:
        status = "UNBOUNDED"
    else:
        status = "ERROR"
    objective = float(raw.fun) if vector is not None and getattr(raw, "fun", None) is not None else None
    return SolveResult(status=status, message=str(raw.message), objective_value=objective, vector=vector, raw_result=raw)


def extract_placements(
    result: SolveResult, problem: MilpProblem, items: list[Item], containers: list[Container], *, tolerance: float,
) -> list[Placement]:
    if result.vector is None or result.status not in {"OPTIMAL", "FEASIBLE_TIME_LIMIT"}:
        raise ValueError(f"Cannot extract placements from solver status {result.status}")
    vector = result.vector
    placements: list[Placement] = []
    for i, item in enumerate(items):
        assignments = [k for k in range(len(containers)) if vector[problem.indices.a(i, k)] > 0.5]
        if len(assignments) != 1:
            raise ValueError(f"Solver vector assigns item {item.item_id} to {len(assignments)} containers")
        k = assignments[0]
        coordinates = [float(vector[index]) for index in (problem.indices.x(i), problem.indices.y(i), problem.indices.z(i))]
        coordinates = [0.0 if abs(value) < tolerance else value for value in coordinates]
        placements.append(Placement(
            item_id=item.item_id, container_id=containers[k].container_id,
            x_mm=coordinates[0], y_mm=coordinates[1], z_mm=coordinates[2],
            length_mm=item.length_mm, width_mm=item.width_mm, height_mm=item.height_mm,
            weight_kg=item.weight_kg,
        ))
    return placements


def solve_level1(
    items: list[Item], containers: list[Container], settings: dict[str, Any] | None = None,
) -> AlgorithmOutcome:
    settings = settings or {}
    problem = build_level1_model(items, containers)
    result = solve_milp(problem, settings)
    tolerance = float(settings.get("coordinate_tolerance_mm", 1e-4))
    placements = [] if result.vector is None else extract_placements(
        result, problem, items, containers, tolerance=tolerance,
    )
    return AlgorithmOutcome(
        solve=result,
        placements=placements,
        backend="scipy.optimize.milp/HiGHS",
        metadata={**problem.metadata, "algorithm_kind": "exact_milp", "optimality_proven": result.status == "OPTIMAL"},
    )
