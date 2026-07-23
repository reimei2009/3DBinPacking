"""SciPy/HiGHS solver adapter and Level 1 solution extraction."""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.optimize import milp

from ..contracts import AlgorithmOutcome
from ...models.common.fixed_orientation_milp import MilpProblem
from ...models.level_01.milp_model import build_level1_model
from ...models.level_02.milp_model import build_level2_model
from ...models.level_03.milp_model import build_level3_model
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


def _solver_diagnostics(result: SolveResult) -> dict[str, Any]:
    """Normalize optional HiGHS MIP diagnostics for reports and previews."""
    diagnostics: dict[str, Any] = {}
    for source in ("mip_gap", "mip_dual_bound", "mip_node_count"):
        value = getattr(result.raw_result, source, None)
        if value is None:
            continue
        if isinstance(value, (float, np.floating)) and not np.isfinite(value):
            continue
        diagnostics[source] = int(value) if source == "mip_node_count" else float(value)
    return diagnostics


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
        metadata={
            **problem.metadata,
            "algorithm_kind": "exact_milp",
            "optimality_proven": result.status == "OPTIMAL",
            **_solver_diagnostics(result),
        },
    )


def solve_level2(
    items: list[Item], containers: list[Container], settings: dict[str, Any] | None = None,
) -> AlgorithmOutcome:
    """Solve fixed-orientation packing with Level 2 geometric support constraints."""
    settings = settings or {}
    problem = build_level2_model(items, containers, settings.get("support", {}))
    result = solve_milp(problem, settings)
    tolerance = float(settings.get("coordinate_tolerance_mm", 1e-4))
    placements = [] if result.vector is None else extract_placements(
        result, problem, items, containers, tolerance=tolerance,
    )
    decision_audit = _audit_level2_support_vector(
        result.vector, problem, items, containers, placements, tolerance=tolerance,
    ) if result.vector is not None else {"model_support_audit_valid": None, "model_support_audit_issue_count": 0}
    return AlgorithmOutcome(
        solve=result,
        placements=placements,
        backend="scipy.optimize.milp/HiGHS",
        metadata={
            **problem.metadata,
            "algorithm_kind": "exact_milp_support",
            "optimality_proven": result.status == "OPTIMAL",
            **_solver_diagnostics(result),
            **decision_audit,
        },
    )


def extract_level3_placements(
    result: SolveResult, problem: MilpProblem, items: list[Item], containers: list[Container], *, tolerance: float,
) -> list[Placement]:
    """Decode the selected horizontal orientation alongside each placement."""
    if result.vector is None or result.status not in {"OPTIMAL", "FEASIBLE_TIME_LIMIT"}:
        raise ValueError(f"Cannot extract placements from solver status {result.status}")
    vector = result.vector
    placements: list[Placement] = []
    for i, item in enumerate(items):
        assignments = [k for k in range(len(containers)) if vector[problem.indices.a(i, k)] > 0.5]
        if len(assignments) != 1:
            raise ValueError(f"Solver vector assigns item {item.item_id} to {len(assignments)} containers")
        orientations = [code for code in (0, 1) if vector[problem.indices.orientation(i, code)] > 0.5]
        if len(orientations) != 1:
            raise ValueError(f"Solver vector selects {len(orientations)} orientations for item {item.item_id}")
        orientation_code = ("XYZ", "YXZ")[orientations[0]]
        length_mm, width_mm = (
            (item.length_mm, item.width_mm)
            if orientation_code == "XYZ"
            else (item.width_mm, item.length_mm)
        )
        coordinates = [float(vector[index]) for index in (problem.indices.x(i), problem.indices.y(i), problem.indices.z(i))]
        coordinates = [0.0 if abs(value) < tolerance else value for value in coordinates]
        placements.append(Placement(
            item_id=item.item_id,
            container_id=containers[assignments[0]].container_id,
            x_mm=coordinates[0],
            y_mm=coordinates[1],
            z_mm=coordinates[2],
            length_mm=length_mm,
            width_mm=width_mm,
            height_mm=item.height_mm,
            weight_kg=item.weight_kg,
            orientation_code=orientation_code,
        ))
    return placements


def solve_level3(
    items: list[Item], containers: list[Container], settings: dict[str, Any] | None = None,
) -> AlgorithmOutcome:
    """Solve a small Level 3 instance as an exact orientation reference.

    This reference is intentionally capped by the Level 3 dispatcher; it is
    not the practical solver for medium or large experiments.
    """
    settings = settings or {}
    problem = build_level3_model(items, containers, settings.get("support", {}))
    result = solve_milp(problem, settings)
    tolerance = float(settings.get("coordinate_tolerance_mm", 1e-4))
    placements = [] if result.vector is None else extract_level3_placements(
        result, problem, items, containers, tolerance=tolerance,
    )
    decision_audit = _audit_level2_support_vector(
        result.vector, problem, items, containers, placements, tolerance=tolerance,
    ) if result.vector is not None else {"model_support_audit_valid": None, "model_support_audit_issue_count": 0}
    return AlgorithmOutcome(
        solve=result,
        placements=placements,
        backend="scipy.optimize.milp/HiGHS",
        metadata={
            **problem.metadata,
            "algorithm_kind": "exact_milp_horizontal_orientation_support",
            "algorithm_role": "exact_reference",
            "optimality_proven": result.status == "OPTIMAL",
            **_solver_diagnostics(result),
            **decision_audit,
        },
    )


def _audit_level2_support_vector(vector, problem, items, containers, placements, *, tolerance: float) -> dict[str, Any]:
    """Check active support binaries against decoded geometry as a solver diagnostic."""
    indices = problem.indices
    placement_map = {value.item_id: value for value in placements}
    issues: list[str] = []
    for i, item_i in enumerate(items):
        placed_i = placement_map[item_i.item_id]
        for k, container in enumerate(containers):
            if vector[indices.floor(i, k)] > 0.5 and (
                placed_i.container_id != container.container_id or abs(placed_i.z_mm) > tolerance
            ):
                issues.append(f"floor({item_i.item_id},{container.container_id}) does not match decoded geometry")
            for j, item_j in enumerate(items):
                if i == j:
                    continue
                placed_j = placement_map[item_j.item_id]
                center = indices.center_support(i, j, k)
                if vector[center] > 0.5 and not _support_point_matches(
                    placed_i, placed_j, container.container_id,
                    placed_i.x_mm + placed_i.length_mm / 2,
                    placed_i.y_mm + placed_i.width_mm / 2,
                    tolerance,
                ):
                    issues.append(f"center_support({item_i.item_id},{item_j.item_id},{container.container_id}) mismatch")
                for p in range(indices.grid_x):
                    point_x = placed_i.x_mm + ((p + 0.5) / indices.grid_x) * placed_i.length_mm
                    for q in range(indices.grid_y):
                        column = indices.support_point(i, j, k, p, q)
                        point_y = placed_i.y_mm + ((q + 0.5) / indices.grid_y) * placed_i.width_mm
                        if vector[column] > 0.5 and not _support_point_matches(
                            placed_i, placed_j, container.container_id, point_x, point_y, tolerance,
                        ):
                            issues.append(
                                f"support_point({item_i.item_id},{item_j.item_id},{container.container_id},{p},{q}) mismatch"
                            )
    return {
        "model_support_audit_valid": not issues,
        "model_support_audit_issue_count": len(issues),
        "model_support_audit_examples": issues[:10],
    }


def _support_point_matches(item, supporter, container_id: str, point_x: float, point_y: float, tolerance: float) -> bool:
    return (
        item.container_id == supporter.container_id == container_id
        and abs(item.z_mm - (supporter.z_mm + supporter.height_mm)) <= tolerance
        and supporter.x_mm - tolerance <= point_x <= supporter.x_mm + supporter.length_mm + tolerance
        and supporter.y_mm - tolerance <= point_y <= supporter.y_mm + supporter.width_mm + tolerance
    )
