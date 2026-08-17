"""Level 5 constructive dispatch with recursive static load-bearing feasibility."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..algorithms.feasibility import ExactSupportFeasibilityPolicy, PlacementFeasibilityPolicy
from ..geometry.contact_index import PlacementFeasibilityContext
from ..algorithms.heuristics.extreme_point_best_fit import solve as solve_extreme_point_best_fit
from ..algorithms.heuristics.extreme_point_ffd import solve as solve_extreme_point_ffd
from ..algorithms.heuristics.extreme_point_hill_climbing import solve as solve_extreme_point_hill_climbing
from ..algorithms.heuristics.maximal_space_best_fit import solve as solve_maximal_space_best_fit
from ..algorithms.metaheuristics.extreme_point_simulated_annealing import solve as solve_extreme_point_simulated_annealing
from ..algorithms.orientation import horizontal_orientation_provider
from ..algorithms.search import exact_support_closures, InventoryLevelAdapter
from ..schemas import Container, Item, Placement
from .level_04_algorithms import ExactSupportStackabilityPolicy
from .level_04_validation import validate_solution as validate_level4_solution
from .level_05_validation import validate_load_bearing
from .load_bearing import LoadBearingAttributes, resolve_load_bearing_attributes
from .load_transfer import LoadTransferError, evaluate_load_transfer
from .stackability import (
    StackabilitySettings,
    attributes_for_item,
    infer_parent_relations,
)


_INVENTORY_SEARCH_ALGORITHMS = frozenset({
    "extreme_point_best_fit", "extreme_point_ffd", "maximal_space_best_fit",
})
_HORIZONTAL_ORIENTATION_PROVIDER = horizontal_orientation_provider()
_INVENTORY_ADAPTER = InventoryLevelAdapter(
    level_id="level_05",
    supported_algorithm_ids=_INVENTORY_SEARCH_ALGORITHMS,
    orientation_provider=_HORIZONTAL_ORIENTATION_PROVIDER,
)


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
        context: PlacementFeasibilityContext | None = None,
    ) -> bool:
        if not self.base.allows(
            container,
            existing,
            candidate,
            loaded_weight_kg=loaded_weight_kg,
            tolerance=tolerance,
            context=context,
        ):
            return False
        try:
            evaluation = evaluate_load_transfer(
                [*existing, candidate],
                self.attributes,
                epsilon_mm=self.epsilon_mm,
                supporter_lookup=(
                    None if context is None
                    else lambda child: context.supporters(
                        child, epsilon_mm=self.epsilon_mm,
                    )
                ),
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
        "maximal_space_best_fit": solve_maximal_space_best_fit,
        "extreme_point_hill_climbing": solve_extreme_point_hill_climbing,
        "extreme_point_simulated_annealing": solve_extreme_point_simulated_annealing,
    }
    try:
        executor = executors[algorithm_id]
    except KeyError as exc:
        raise ValueError(
            "Level 5 implements Extreme Point Best Fit, FFD, Maximal Empty Spaces "
            "Best Fit, Hill Climbing, and Simulated Annealing; "
            "other solvers remain inactive."
        ) from exc
    support = settings.get("support", {})
    stackability = settings.get("stackability", {})
    load_bearing = settings.get("load_bearing", {})
    validation = settings.get("validation", {})
    support_threshold = float(support.get("threshold", 0.8))
    support_epsilon = float(support.get("epsilon_mm", 1e-4))
    load_tolerance = float(
        validation.get(
            "load_tolerance_kg", settings.get("load_tolerance_kg", 1e-6),
        )
    )
    stack_settings = StackabilitySettings.from_config(stackability)
    stack_attributes = {
        item.item_id: attributes_for_item(item, stack_settings) for item in items
    }

    def execute_with_load_bearing(
        selected_items: list[Item],
        selected_containers: list[Container],
        selected_settings: dict[str, Any],
        *,
        container_subset_policy: Any = None,
    ):
        # Partial repack may pass only the items being rebuilt while retaining
        # seeded placements. The load graph still needs attributes for every
        # original item, including those seeded placements.
        load_policy = build_level_05_feasibility_policy(items, selected_settings)
        solver_settings = dict(selected_settings)
        if algorithm_id in {
            "extreme_point_hill_climbing", "extreme_point_simulated_annealing",
        }:
            solver_settings.setdefault("initial_constructor", "extreme_point_best_fit")
            solver_settings.setdefault("repair_constructor", "extreme_point_best_fit")
        keyword_arguments: dict[str, Any] = {
            "policy": load_policy,
            "orientation_provider": _HORIZONTAL_ORIENTATION_PROVIDER,
        }
        if container_subset_policy is not None:
            keyword_arguments["container_subset_policy"] = container_subset_policy
        return executor(
            selected_items,
            selected_containers,
            solver_settings,
            **keyword_arguments,
        )

    def candidate_validator(placements: list[Placement]) -> bool:
        parent_relations = infer_parent_relations(
            placements, stack_attributes, epsilon_mm=support_epsilon,
        )
        level4 = validate_level4_solution(
            items,
            containers,
            placements,
            parent_relations,
            stackability,
            support_threshold=support_threshold,
            support_epsilon_mm=support_epsilon,
            coordinate_tolerance=float(
                validation.get("coordinate_tolerance_mm", 1e-4)
            ),
            weight_tolerance=float(validation.get("weight_tolerance_kg", 1e-6)),
        )
        if not level4.result.valid:
            return False
        load = validate_load_bearing(
            items,
            placements,
            load_bearing,
            epsilon_mm=support_epsilon,
            load_tolerance_kg=load_tolerance,
        )
        return load.result.valid

    return _INVENTORY_ADAPTER.execute(
        algorithm_id=algorithm_id,
        items=items,
        containers=containers,
        settings=settings,
        executor=execute_with_load_bearing,
        candidate_validator=candidate_validator,
        support_closure_provider=lambda placements: exact_support_closures(
            placements, epsilon_mm=support_epsilon,
        ),
        secondary_support_threshold=support_threshold,
        secondary_support_epsilon_mm=support_epsilon,
    )


def build_level_05_feasibility_policy(
    items: list[Item],
    settings: dict[str, Any],
    *,
    support_policy_id: str = "horizontal_orientation_geometry_payload_exact_support",
    policy_id: str = "horizontal_orientation_geometry_payload_exact_support_stackability_load_bearing",
) -> LoadBearingFeasibilityPolicy:
    """Create the shared Level 5 external feasibility stack for compound consumers too."""
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
        policy_id=support_policy_id,
    )
    stack_policy = ExactSupportStackabilityPolicy(
        attributes=stack_attributes,
        epsilon_mm=float(support.get("epsilon_mm", 1e-4)),
        base=support_policy,
    )
    return LoadBearingFeasibilityPolicy(
        attributes=resolve_load_bearing_attributes(items, load_bearing),
        epsilon_mm=float(support.get("epsilon_mm", 1e-4)),
        load_tolerance_kg=float(
            settings.get("validation", {}).get(
                "load_tolerance_kg", settings.get("load_tolerance_kg", 1e-6),
            )
        ),
        base=stack_policy,
        capacity_profile=str(load_bearing.get("capacity_profile", {}).get("mode", "")),
        policy_id=policy_id,
    )
