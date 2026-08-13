"""Canonical contracts returned by packing and bounded-search algorithms."""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite
from time import perf_counter
from typing import Any

from ..schemas import Placement, SolveResult


@dataclass
class AlgorithmOutcome:
    solve: SolveResult
    placements: list[Placement]
    backend: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, order=True)
class OfficialObjective:
    """Mục tiêu lexicographic chính thức, độc lập kích thước catalog."""

    used_container_count: int
    total_container_cost: float

    def as_dict(self) -> dict[str, int | float]:
        return {
            "used_container_count": self.used_container_count,
            "total_container_cost": self.total_container_cost,
        }


@dataclass(frozen=True, order=True)
class SecondarySearchScore:
    """Tie-break chuẩn hóa; giá trị nhỏ hơn tốt hơn.

    Score này chỉ có ý nghĩa sau khi candidate complete đã qua independent
    validation. Nó không được phép thay đổi thứ tự objective chính thức.
    """

    negative_utilization_concentration: float
    internal_void_ratio: float
    negative_minimum_support_margin: float
    placement_signature: str

    def as_dict(self) -> dict[str, float | str]:
        return {
            "utilization_concentration": -self.negative_utilization_concentration,
            "internal_void_ratio": self.internal_void_ratio,
            "minimum_support_margin": -self.negative_minimum_support_margin,
            "placement_signature": self.placement_signature,
        }


class ConstructionTerminationReason(StrEnum):
    """Lý do một construction attempt kết thúc."""

    COMPLETE = "COMPLETE"
    NO_FEASIBLE_CANDIDATE = "NO_FEASIBLE_CANDIDATE"
    TIME_LIMIT_REACHED = "TIME_LIMIT_REACHED"
    NOT_ATTEMPTED_AFTER_FAILURE = "NOT_ATTEMPTED_AFTER_FAILURE"


class SearchTerminationReason(StrEnum):
    """Lý do dừng canonical dành cho time-bounded search."""

    COMPLETED = "COMPLETED"
    TIME_LIMIT_REACHED = "TIME_LIMIT_REACHED"
    ATTEMPT_LIMIT_REACHED = "ATTEMPT_LIMIT_REACHED"
    SUBSET_LIMIT_REACHED = "SUBSET_LIMIT_REACHED"
    ITEM_ORDER_LIMIT_REACHED = "ITEM_ORDER_LIMIT_REACHED"
    CONTAINER_ORDER_LIMIT_REACHED = "CONTAINER_ORDER_LIMIT_REACHED"
    CANDIDATE_LIMIT_REACHED = "CANDIDATE_LIMIT_REACHED"
    REPAIR_LIMIT_REACHED = "REPAIR_LIMIT_REACHED"
    NO_IMPROVEMENT_LIMIT_REACHED = "NO_IMPROVEMENT_LIMIT_REACHED"


@dataclass(frozen=True)
class AttemptStatistics:
    """Các bộ đếm cục bộ của đúng một construction attempt."""

    containers_tested: int = 0
    candidate_positions_tested: int = 0
    orientations_tested: int = 0


@dataclass(frozen=True)
class UnpackedItemDiagnostic:
    """Bằng chứng chẩn đoán cho một item chưa được xếp trong attempt."""

    item_id: str
    reason_code: str
    containers_tested: int = 0
    orientations_tested: int = 0
    candidate_positions_tested: int = 0
    boundary_rejections: int = 0
    overlap_rejections: int = 0
    payload_rejections: int = 0
    support_rejections: int = 0
    stackability_rejections: int = 0
    load_bearing_rejections: int = 0
    repair_attempts: int = 0
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ConstructionAttemptResult(Sequence[Placement]):
    """Kết quả đầy đủ hoặc partial của một lần constructive packing.

    Object vẫn có giao diện sequence chỉ để các extension hiện hữu có thể đọc
    placements trong giai đoạn migration. Thuộc tính ``complete`` mới là nguồn
    sự thật để quyết định đây có phải candidate nghiệm hoàn chỉnh hay không.
    """

    complete: bool
    placements: tuple[Placement, ...]
    unpacked_items: tuple[UnpackedItemDiagnostic, ...]
    failed_item_id: str | None
    termination_reason: str
    attempt_signature: str
    statistics: AttemptStatistics = field(default_factory=AttemptStatistics)
    subset_ids: tuple[str, ...] = ()
    container_order: tuple[str, ...] = ()
    item_order_id: str = "explicit_order"
    algorithm_id: str = "constructive"
    search_score: tuple[float, ...] | None = None

    def __len__(self) -> int:
        return len(self.placements)

    def __getitem__(self, index):  # type: ignore[no-untyped-def]
        return self.placements[index]

    def __iter__(self) -> Iterator[Placement]:
        return iter(self.placements)

    def metadata(self) -> dict[str, Any]:
        return {
            "construction_complete": self.complete,
            "construction_termination_reason": self.termination_reason,
            "construction_failed_item_id": self.failed_item_id,
            "best_partial_placement_count": (
                0 if self.complete else len(self.placements)
            ),
            "unpacked_item_count": len(self.unpacked_items),
            "unpacked_items": [
                {
                    "item_id": value.item_id,
                    "reason_code": value.reason_code,
                    "containers_tested": value.containers_tested,
                    "orientations_tested": value.orientations_tested,
                    "candidate_positions_tested": value.candidate_positions_tested,
                }
                for value in self.unpacked_items
            ],
            "construction_attempt_signature": self.attempt_signature,
        }


@dataclass(frozen=True)
class ValidatedIncumbent:
    """Bản ghi canonical của candidate complete đã qua independent validation."""

    outcome: AlgorithmOutcome
    objective: OfficialObjective
    placement_signature: str
    secondary_score: SecondarySearchScore | None = None


@dataclass
class SearchBudget:
    """Budget dùng chung cho construction, repair và validation reserve."""

    search_deadline_monotonic: float
    total_deadline_monotonic: float
    max_attempts: int
    max_subsets: int
    max_item_orders: int
    max_container_orders: int
    max_candidate_evaluations: int
    max_repair_attempts: int
    max_no_improvement_attempts: int
    started_at_monotonic: float = field(default_factory=perf_counter)
    attempts: int = 0
    subsets: int = 0
    item_orders: int = 0
    container_orders: int = 0
    candidate_evaluations: int = 0
    repair_attempts: int = 0
    no_improvement_attempts: int = 0
    _clock: Callable[[], float] = field(default=perf_counter, repr=False, compare=False)

    def __post_init__(self) -> None:
        limits = {
            "max_attempts": self.max_attempts,
            "max_subsets": self.max_subsets,
            "max_item_orders": self.max_item_orders,
            "max_container_orders": self.max_container_orders,
            "max_candidate_evaluations": self.max_candidate_evaluations,
            "max_repair_attempts": self.max_repair_attempts,
            "max_no_improvement_attempts": self.max_no_improvement_attempts,
        }
        invalid = [name for name, value in limits.items() if value <= 0]
        if invalid:
            raise ValueError("Search-budget limits must be positive: " + ", ".join(invalid))
        if not all(isfinite(value) for value in (
            self.started_at_monotonic,
            self.search_deadline_monotonic,
            self.total_deadline_monotonic,
        )):
            raise ValueError("search-budget timestamps must be finite")
        if self.search_deadline_monotonic > self.total_deadline_monotonic:
            raise ValueError("search deadline cannot be later than total deadline")

    def search_time_exhausted(self) -> bool:
        return self._clock() >= self.search_deadline_monotonic

    def total_time_exhausted(self) -> bool:
        return self._clock() >= self.total_deadline_monotonic

    def can_start_attempt(self) -> bool:
        return not self.search_time_exhausted() and self.attempts < self.max_attempts

    def record_attempt(self) -> bool:
        self.attempts += 1
        return self.attempts <= self.max_attempts

    def record_subset(self, count: int = 1) -> bool:
        if count < 0:
            raise ValueError("subset count cannot be negative")
        self.subsets += count
        return self.subsets <= self.max_subsets

    def record_item_order(self) -> bool:
        self.item_orders += 1
        return self.item_orders <= self.max_item_orders

    def record_container_order(self) -> bool:
        self.container_orders += 1
        return self.container_orders <= self.max_container_orders

    def record_candidate(self, count: int = 1) -> bool:
        if count < 0:
            raise ValueError("candidate count cannot be negative")
        self.candidate_evaluations += count
        return self.candidate_evaluations <= self.max_candidate_evaluations

    def record_repair(self, count: int = 1) -> bool:
        if count < 0:
            raise ValueError("repair count cannot be negative")
        self.repair_attempts += count
        return self.repair_attempts <= self.max_repair_attempts

    def record_no_improvement(self) -> bool:
        self.no_improvement_attempts += 1
        return self.no_improvement_attempts <= self.max_no_improvement_attempts

    def reset_no_improvement(self) -> None:
        self.no_improvement_attempts = 0

    def stop_reason(self) -> SearchTerminationReason | None:
        if self.search_time_exhausted():
            return SearchTerminationReason.TIME_LIMIT_REACHED
        if self.attempts >= self.max_attempts:
            return SearchTerminationReason.ATTEMPT_LIMIT_REACHED
        if self.subsets >= self.max_subsets:
            return SearchTerminationReason.SUBSET_LIMIT_REACHED
        if self.item_orders >= self.max_item_orders:
            return SearchTerminationReason.ITEM_ORDER_LIMIT_REACHED
        if self.container_orders >= self.max_container_orders:
            return SearchTerminationReason.CONTAINER_ORDER_LIMIT_REACHED
        if self.candidate_evaluations >= self.max_candidate_evaluations:
            return SearchTerminationReason.CANDIDATE_LIMIT_REACHED
        if self.repair_attempts >= self.max_repair_attempts:
            return SearchTerminationReason.REPAIR_LIMIT_REACHED
        if self.no_improvement_attempts >= self.max_no_improvement_attempts:
            return SearchTerminationReason.NO_IMPROVEMENT_LIMIT_REACHED
        return None

    def snapshot(self) -> dict[str, int | float | str | None]:
        reason = self.stop_reason()
        return {
            "started_at_monotonic": self.started_at_monotonic,
            "search_deadline_monotonic": self.search_deadline_monotonic,
            "total_deadline_monotonic": self.total_deadline_monotonic,
            "attempts": self.attempts,
            "subsets": self.subsets,
            "item_orders": self.item_orders,
            "container_orders": self.container_orders,
            "candidate_evaluations": self.candidate_evaluations,
            "repair_attempts": self.repair_attempts,
            "no_improvement_attempts": self.no_improvement_attempts,
            "stop_reason": None if reason is None else str(reason),
        }
