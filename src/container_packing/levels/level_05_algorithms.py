"""Level 5 constructive dispatch with recursive static load-bearing feasibility."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..algorithms.feasibility import ExactSupportFeasibilityPolicy, PlacementFeasibilityPolicy
from ..algorithms.heuristics.extreme_point_best_fit import solve as solve_extreme_point_best_fit
from ..algorithms.heuristics.extreme_point_ffd import solve as solve_extreme_point_ffd
from ..algorithms.heuristics.extreme_point_hill_climbing import solve as solve_extreme_point_hill_climbing
from ..algorithms.metaheuristics.extreme_point_simulated_annealing import solve as solve_extreme_point_simulated_annealing
from ..algorithms.orientation import horizontal_orientation_provider
from ..schemas import Container, Item, Placement
from .level_04_algorithms import ExactSupportStackabilityPolicy
from .load_bearing import LoadBearingAttributes, resolve_load_bearing_attributes
from .load_transfer import LoadTransferError, evaluate_load_transfer
from .stackability import StackabilitySettings, attributes_for_item


@dataclass
class LoadBearingFeasibilityPolicy:
    """Compose Level 4 feasibility with exact recursive static load transfer."""

    attributes: dict[str, LoadBearingAttributes]
    epsilon_mm: float
    load_tolerance_kg: float
    base: PlacementFeasibilityPolicy
    capacity_profile: str
    policy_id: str = (
        "horizontal_orientation_geometry_payload_exact_support_"
        "stackability_load_bearing"
    )
    load_bearing_rejected_candidates: int = 0
    load_bearing_valid_candidates: int = 0

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
            container,
            existing,
            candidate,
            loaded_weight_kg=loaded_weight_kg,
            tolerance=tolerance,
        ):
            return False
        try:
            evaluation = evaluate_load_transfer(
                [*existing, candidate],
                self.attributes,
                epsilon_mm=self.epsilon_mm,
            )
        except LoadTransferError:
            self.load_bearing_rejected_candidates += 1
            return False
        valid = all(
            record.load_above_kg
            <= record.max_supported_weight_kg + self.load_tolerance_kg
            and (
                not record.is_fragile
                or record.load_above_kg <= self.load_tolerance_kg
            )
            for record in evaluation.records
        )
        if valid:
            self.load_bearing_valid_candidates += 1
        else:
            self.load_bearing_rejected_candidates += 1
        return valid

    def metadata(self) -> dict[str, Any]:
        return {
            **self.base.metadata(),
            "feasibility_policy": self.policy_id,
            "load_bearing_capacity_profile": self.capacity_profile,
            "load_transfer_model": "static_vertical_contact_area_recursive_v1",
            "load_bearing_rejected_candidates": self.load_bearing_rejected_candidates,
            "load_bearing_valid_candidates": self.load_bearing_valid_candidates,
        }


def execute_level_05(
    algorithm_id: str,
    items: list[Item],
    containers: list[Container],
    settings: dict[str, Any],
):
    executors = {
        "extreme_point_best_fit": solve_extreme_point_best_fit,
        "extreme_point_ffd": solve_extreme_point_ffd,
        "extreme_point_hill_climbing": solve_extreme_point_hill_climbing,
        "extreme_point_simulated_annealing": solve_extreme_point_simulated_annealing,
    }
    try:
        executor = executors[algorithm_id]
    except KeyError as exc:
        raise ValueError(
            "Level 5 checkpoint implements Extreme Point Best Fit, FFD, Hill Climbing, "
            "and Simulated Annealing; "
            "other solvers remain inactive."
        ) from exc
    support = settings.get("support", {})
    stackability = settings.get("stackability", {})
    load_bearing = settings.get("load_bearing", {})
    stack_settings = StackabilitySettings.from_config(stackability)
    stack_attributes = {
        item.item_id: attributes_for_item(item, stack_settings) for item in items
    }
    support_policy = ExactSupportFeasibilityPolicy(
        threshold=float(support.get("threshold", 0.8)),
        epsilon_mm=float(support.get("epsilon_mm", 1e-4)),
        policy_id="horizontal_orientation_geometry_payload_exact_support",
    )
    stack_policy = ExactSupportStackabilityPolicy(
        attributes=stack_attributes,
        epsilon_mm=float(support.get("epsilon_mm", 1e-4)),
        base=support_policy,
    )
    load_policy = LoadBearingFeasibilityPolicy(
        attributes=resolve_load_bearing_attributes(items, load_bearing),
        epsilon_mm=float(support.get("epsilon_mm", 1e-4)),
        load_tolerance_kg=float(settings.get("load_tolerance_kg", 1e-6)),
        base=stack_policy,
        capacity_profile=str(load_bearing.get("capacity_profile", {}).get("mode", "")),
    )
    solver_settings = dict(settings)
    if algorithm_id in {
        "extreme_point_hill_climbing", "extreme_point_simulated_annealing",
    }:
        solver_settings.setdefault("initial_constructor", "extreme_point_best_fit")
        solver_settings.setdefault("repair_constructor", "extreme_point_best_fit")
    return executor(
        items,
        containers,
        solver_settings,
        policy=load_policy,
        orientation_provider=horizontal_orientation_provider(),
    )
