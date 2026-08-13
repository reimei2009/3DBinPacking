"""Composition adapter giữa inventory orchestration và contract từng level."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..contracts import AlgorithmOutcome
from ..orientation import OrientationProvider
from ...schemas import Container, Item
from .configuration import ContainerSearchConfiguration
from .incumbent import CandidateValidator
from .inventory_consolidation import SupportClosureProvider
from .inventory_orchestration import (
    InventoryConstructiveExecutor,
    InventorySearchOrchestrator,
    InventorySearchRequest,
)


@dataclass
class InventoryLevelAdapter:
    """Nối một executor level-aware vào canonical inventory workflow.

    Executor chịu trách nhiệm feasibility policy của level. Adapter chỉ quyết định
    khi nào dùng inventory orchestration và chuyển đầy đủ orientation/validator/
    support closure vào shared search.
    """

    level_id: str
    supported_algorithm_ids: frozenset[str]
    orientation_provider: OrientationProvider
    orchestrator: InventorySearchOrchestrator = field(
        default_factory=InventorySearchOrchestrator,
    )

    def execute(
        self,
        *,
        algorithm_id: str,
        items: list[Item],
        containers: list[Container],
        settings: dict[str, Any],
        executor: InventoryConstructiveExecutor,
        candidate_validator: CandidateValidator,
        support_closure_provider: SupportClosureProvider | None = None,
        secondary_support_threshold: float | None = None,
        secondary_support_epsilon_mm: float = 1e-4,
    ) -> AlgorithmOutcome:
        search = ContainerSearchConfiguration.from_mapping(
            settings.get("container_search")
        )
        if not search.enabled:
            return executor(items, containers, settings)
        return self.orchestrator.execute(
            InventorySearchRequest(
                algorithm_id=algorithm_id,
                items=items,
                containers=containers,
                settings=settings,
                configuration=search,
                supported_algorithm_ids=self.supported_algorithm_ids,
                orientation_provider=self.orientation_provider,
                precheck_backend=f"inventory-aware-{self.level_id}-precheck",
                precheck_failure_context=f"{self.level_id} instance",
                support_closure_provider=support_closure_provider,
                candidate_validator=candidate_validator,
                secondary_support_threshold=secondary_support_threshold,
                secondary_support_epsilon_mm=secondary_support_epsilon_mm,
            ),
            executor,
        )
