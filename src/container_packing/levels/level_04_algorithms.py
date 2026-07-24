"""Level 4 solver dispatch: Level 3 support/orientation plus stackability."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..algorithms.feasibility import ExactSupportFeasibilityPolicy, PlacementFeasibilityPolicy
from ..algorithms.heuristics.extreme_point_best_fit import solve as solve_extreme_point_best_fit
from ..algorithms.heuristics.extreme_point_ffd import solve as solve_extreme_point_ffd
from ..algorithms.heuristics.extreme_point_hill_climbing import solve as solve_extreme_point_hill_climbing
from ..algorithms.heuristics.maximal_space_best_fit import solve as solve_maximal_space_best_fit
from ..algorithms.metaheuristics.extreme_point_simulated_annealing import solve as solve_extreme_point_simulated_annealing
from ..algorithms.orientation import horizontal_orientation_provider
from ..schemas import Container, Item, Placement
from .stackability import (
    StackabilityAttributes,
    StackabilitySettings,
    attributes_for_item,
    chain_respects_max_layers,
    infer_parent_relations,
)


@dataclass
class ExactSupportStackabilityPolicy:
    """Compose support feasibility with Level 4 stack compatibility and depth."""

    attributes: dict[str, StackabilityAttributes]
    epsilon_mm: float
    base: PlacementFeasibilityPolicy
    policy_id: str = "horizontal_orientation_geometry_payload_exact_support_stackability"
    stackability_rejected_candidates: int = 0
    stackability_valid_candidates: int = 0

    def allows(
        self,
        container: Container,
        existing: list[Placement],
        candidate: Placement,
        *,
        loaded_weight_kg: float,
        tolerance: float,
    ) -> bool:
        if not self.base.allows(
            container, existing, candidate,
            loaded_weight_kg=loaded_weight_kg, tolerance=tolerance,
        ):
            return False
        candidate_attributes = self.attributes[candidate.item_id]
        if abs(candidate.z_mm) <= self.epsilon_mm:
            self.stackability_valid_candidates += 1
            return True
        if candidate_attributes.is_non_stackable:
            self.stackability_rejected_candidates += 1
            return False
        projected = [*existing, candidate]
        relations = infer_parent_relations(projected, self.attributes, epsilon_mm=self.epsilon_mm)
        relation = next((value for value in relations if value.child_item_id == candidate.item_id), None)
        valid = relation is not None and chain_respects_max_layers(candidate.item_id, relations, self.attributes)
        if valid:
            self.stackability_valid_candidates += 1
        else:
            self.stackability_rejected_candidates += 1
        return valid

    def metadata(self) -> dict[str, Any]:
        return {
            **self.base.metadata(),
            "feasibility_policy": self.policy_id,
            "stackability_rejected_candidates": self.stackability_rejected_candidates,
            "stackability_valid_candidates": self.stackability_valid_candidates,
            "stackability_parent_selection": "largest_contact_area_then_item_id",
            "stackability_max_layers_semantics": "maximum_layers_in_parent_chain_including_root",
        }


def execute_level_04(
    algorithm_id: str, items: list[Item], containers: list[Container], settings: dict[str, Any]
):
    executors = {
        "extreme_point_ffd": solve_extreme_point_ffd,
        "extreme_point_best_fit": solve_extreme_point_best_fit,
        "maximal_space_best_fit": solve_maximal_space_best_fit,
        "extreme_point_hill_climbing": solve_extreme_point_hill_climbing,
        "extreme_point_simulated_annealing": solve_extreme_point_simulated_annealing,
    }
    try:
        executor = executors[algorithm_id]
    except KeyError as exc:
        raise ValueError(
            "Level 4 implements Extreme Point FFD, Extreme Point Best Fit, "
            "Maximal Empty Spaces Best Fit, Hill Climbing, and Simulated Annealing; "
            "other solvers remain inactive."
        ) from exc
    support = settings.get("support", {})
    stackability = settings.get("stackability", {})
    configured = StackabilitySettings.from_config(stackability)
    attributes = {item.item_id: attributes_for_item(item, configured) for item in items}
    support_policy = ExactSupportFeasibilityPolicy(
        threshold=float(support.get("threshold", 0.8)),
        epsilon_mm=float(support.get("epsilon_mm", 1e-4)),
        policy_id="horizontal_orientation_geometry_payload_exact_support",
    )
    policy = ExactSupportStackabilityPolicy(
        attributes=attributes,
        epsilon_mm=float(support.get("epsilon_mm", 1e-4)),
        base=support_policy,
    )
    solver_settings = dict(settings)
    if algorithm_id in {"extreme_point_hill_climbing", "extreme_point_simulated_annealing"}:
        solver_settings.setdefault("initial_constructor", "extreme_point_best_fit")
        solver_settings.setdefault("repair_constructor", "extreme_point_best_fit")
    return executor(
        items,
        containers,
        solver_settings,
        policy=policy,
        orientation_provider=horizontal_orientation_provider(),
    )
