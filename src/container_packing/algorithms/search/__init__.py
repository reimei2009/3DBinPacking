"""Các primitive dùng chung cho time-bounded container search."""

from .inventory import (
    ContainerTypeComposition,
    ContainerTypeGroup,
    InventorySearchLimits,
    NormalizedContainerInventory,
    normalize_container_inventory,
)
from .configuration import (
    AdaptiveClusterEliminationConfiguration,
    ConsolidationConfiguration,
    ContainerEliminationConfiguration,
    ContainerSearchConfiguration,
)
from .inventory_consolidation import (
    BoundedInventoryConsolidator,
    ConsolidationResult,
    exact_support_closures,
    singleton_support_closures,
)
from .precheck import (
    CapacityLimitAssessment,
    assess_capacity_within_container_limit,
    HardPrecheckIssue,
    HardPrecheckResult,
    LowerBoundEstimate,
    estimate_container_lower_bound,
    run_hard_precheck,
)
from .subset_generation import LazyRankedContainerSubsetPolicy
from .inventory_orchestration import (
    InventoryConstructiveExecutor,
    InventorySearchOrchestrator,
    InventorySearchRequest,
)

__all__ = [
    "ContainerTypeGroup",
    "AdaptiveClusterEliminationConfiguration",
    "ContainerTypeComposition",
    "ContainerSearchConfiguration",
    "ConsolidationConfiguration",
    "ContainerEliminationConfiguration",
    "BoundedInventoryConsolidator",
    "ConsolidationResult",
    "exact_support_closures",
    "singleton_support_closures",
    "HardPrecheckIssue",
    "HardPrecheckResult",
    "InventorySearchLimits",
    "InventoryConstructiveExecutor",
    "InventorySearchOrchestrator",
    "InventorySearchRequest",
    "LazyRankedContainerSubsetPolicy",
    "LowerBoundEstimate",
    "NormalizedContainerInventory",
    "estimate_container_lower_bound",
    "CapacityLimitAssessment",
    "assess_capacity_within_container_limit",
    "normalize_container_inventory",
    "run_hard_precheck",
]
