"""Registry of implemented mathematical level contracts."""

from __future__ import annotations

from pathlib import Path

from ..experiments.contracts import (
    ConstraintDefinition,
    LevelContract,
    LevelDefinition,
    VariableDefinition,
)
from . import level_01

_LEVELS = {
    "level_01": LevelDefinition(
        level_id="level_01",
        description="Fixed orientation; boundary, pairwise non-overlap, and payload constraints",
        default_config=Path("config/level_01/default.yaml"),
        supported_algorithms=(
            "milp_big_m", "extreme_point_ffd", "extreme_point_hill_climbing",
            "extreme_point_simulated_annealing",
        ),
        run=level_01.run,
        prepare=level_01.prepare,
        validate_run=level_01.validate_run,
        contract=LevelContract(
            title="Level 1 — Fixed-orientation 3D container packing",
            problem=(
                "Pack every rectangular item exactly once into heterogeneous containers, "
                "choose its 3D coordinates, and minimize the containers used."
            ),
            objective=(
                "Primary: minimize the number of used containers.",
                "Secondary: minimize the synthetic cost of used containers.",
            ),
            variables=(
                VariableDefinition("u[k]", "binary", "container k", "1 when container k is used"),
                VariableDefinition("a[i,k]", "binary", "item i, container k", "1 when item i is assigned to container k"),
                VariableDefinition("x[i], y[i], z[i]", "continuous", "item i", "fixed-orientation lower-left-back coordinates in mm"),
                VariableDefinition("delta[i,j,k,d]", "binary", "item pair, container, direction", "activates one of six pairwise separation directions in the MILP"),
            ),
            active_constraints=(
                ConstraintDefinition("exact_assignment", "Exact assignment", "Every required item is packed exactly once."),
                ConstraintDefinition("container_activation", "Container activation", "An item can be assigned only to a used container."),
                ConstraintDefinition("boundaries", "Container boundaries", "Every item remains inside its assigned container."),
                ConstraintDefinition("pairwise_non_overlap", "Pairwise non-overlap", "Items in the same container have disjoint interiors."),
                ConstraintDefinition("payload", "Maximum payload", "Loaded weight cannot exceed container payload."),
            ),
            inactive_constraints=(
                "rotation", "support", "floor contact", "stability", "stackability",
                "fragility", "center of gravity", "loading order", "unloading order",
            ),
            assumptions=(
                "Offline input and one physical instance per configured container.",
                "Rectangular cuboids with fixed orientation.",
                "All configured item dimensions are expressed in millimeters and weights in kilograms.",
            ),
            limitations=(
                "Heuristic FEASIBLE status is not a proof of global optimality.",
                "Geometric feasibility does not imply a physically stable loading plan.",
            ),
            solution_claim="Nghiệm hợp lệ về hình học và tải trọng theo giả định Level 1.",
        ),
    ),
}


def list_levels() -> tuple[LevelDefinition, ...]:
    return tuple(_LEVELS[key] for key in sorted(_LEVELS))


def get_level(level_id: str) -> LevelDefinition:
    try:
        return _LEVELS[level_id]
    except KeyError as exc:
        available = ", ".join(sorted(_LEVELS))
        raise ValueError(f"Level {level_id!r} is not implemented. Available: {available}") from exc
