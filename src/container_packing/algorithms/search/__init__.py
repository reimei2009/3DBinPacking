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
    IncumbentAcquisitionConfiguration,
    SecondarySearchScoreConfiguration,
)
from .inventory_consolidation import (
    BoundedInventoryConsolidator,
    ConsolidationResult,
    exact_support_closures,
    singleton_support_closures,
)
from .incumbent import (
    CandidateValidator,
    ValidatedIncumbentStore,
)
from ..contracts import OfficialObjective, SecondarySearchScore
from .secondary_score import calculate_secondary_search_score
from .precheck import (
    CapacityLimitAssessment,
    assess_capacity_within_container_limit,
    HardPrecheckIssue,
    HardPrecheckResult,
    LowerBoundEstimate,
    estimate_container_lower_bound,
    run_hard_precheck,
)
from .subset_generation import (
    LazyRankedContainerSubsetPolicy,
    midpoint_cardinality_ladder,
)
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
    "IncumbentAcquisitionConfiguration",
    "SecondarySearchScoreConfiguration",
    "BoundedInventoryConsolidator",
    "ConsolidationResult",
    "CandidateValidator",
    "OfficialObjective",
    "SecondarySearchScore",
    "calculate_secondary_search_score",
    "ValidatedIncumbentStore",
    "exact_support_closures",
    "singleton_support_closures",
    "HardPrecheckIssue",
    "HardPrecheckResult",
    "InventorySearchLimits",
    "InventoryConstructiveExecutor",
    "InventorySearchOrchestrator",
    "InventorySearchRequest",
    "LazyRankedContainerSubsetPolicy",
    "midpoint_cardinality_ladder",
    "LowerBoundEstimate",
    "NormalizedContainerInventory",
    "estimate_container_lower_bound",
    "CapacityLimitAssessment",
    "assess_capacity_within_container_limit",
    "normalize_container_inventory",
    "run_hard_precheck",
]
