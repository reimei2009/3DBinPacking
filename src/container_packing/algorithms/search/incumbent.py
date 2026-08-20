"""Kho incumbent đã qua kiểm định độc lập cho inventory search."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from ..contracts import (
    AlgorithmOutcome,
    OfficialObjective,
    SecondarySearchScore,
    ValidatedIncumbent,
)
from ...metrics import placement_signature
from ...schemas import Container, Placement


CandidateValidator = Callable[[list[Placement]], bool]
SecondaryScoreFactory = Callable[[list[Placement]], SecondarySearchScore]


class ValidatedIncumbentStore:
    """Chỉ lưu candidate complete, hợp lệ và tốt hơn incumbent hiện tại.

    Các kiểm tra rẻ (status, completeness và objective) chạy trước validator.
    Vì vậy independent validation chỉ được gọi cho candidate có khả năng thay
    incumbent, thay vì cho mọi candidate construction bị loại sớm.
    """

    # Candidate dừng vì time limit có thể còn hữu ích làm diagnostic, nhưng
    # contract hiện tại không cho phép nó trở thành official incumbent.
    _SUCCESS_STATUSES = frozenset({"OPTIMAL", "FEASIBLE"})

    def __init__(
        self,
        *,
        required_item_ids: Sequence[str],
        containers: Sequence[Container],
        validator: CandidateValidator,
        secondary_score_factory: SecondaryScoreFactory | None = None,
    ) -> None:
        if validator is None:
            raise ValueError("ValidatedIncumbentStore requires an independent validator")
        self._required_item_ids = frozenset(required_item_ids)
        if len(self._required_item_ids) != len(required_item_ids):
            raise ValueError("required_item_ids must be unique")
        self._container_costs = {
            value.container_id: float(value.cost) for value in containers
        }
        self._validator = validator
        self._secondary_score_factory = secondary_score_factory
        self._record: ValidatedIncumbent | None = None
        self.candidates_considered = 0
        self.candidates_validated = 0
        self.candidates_rejected_incomplete = 0
        self.candidates_rejected_not_better = 0
        self.candidates_rejected_invalid = 0
        self.improvements_accepted = 0
        self.last_decision = "NOT_CONSIDERED"

    @property
    def record(self) -> ValidatedIncumbent | None:
        return self._record

    @property
    def outcome(self) -> AlgorithmOutcome | None:
        return None if self._record is None else self._record.outcome

    @property
    def objective(self) -> OfficialObjective | None:
        return None if self._record is None else self._record.objective

    def consider(
        self,
        outcome: AlgorithmOutcome,
        *,
        validate_non_improving: bool = False,
    ) -> bool:
        """Kiểm định và nhận candidate nếu nó cải thiện objective chính thức."""

        self.candidates_considered += 1
        if not self._is_complete(outcome):
            self.candidates_rejected_incomplete += 1
            self.last_decision = "INCOMPLETE"
            return False
        objective = self._objective(outcome.placements)
        official_not_better = bool(
            self._record is not None
            and (
                objective > self._record.objective
                or (
                    objective == self._record.objective
                    and self._secondary_score_factory is None
                )
            )
        )
        if official_not_better and not validate_non_improving:
            self.candidates_rejected_not_better += 1
            self.last_decision = "NOT_BETTER_NOT_VALIDATED"
            return False
        self.candidates_validated += 1
        if not self._validator(outcome.placements):
            self.candidates_rejected_invalid += 1
            self.last_decision = "INVALID"
            return False
        secondary_score = (
            None
            if self._secondary_score_factory is None
            else self._secondary_score_factory(outcome.placements)
        )
        if (
            self._record is not None
            and objective == self._record.objective
            and self._record.secondary_score is not None
            and secondary_score is not None
            and secondary_score >= self._record.secondary_score
        ):
            self.candidates_rejected_not_better += 1
            self.last_decision = "VALID_NOT_BETTER"
            return False
        if official_not_better:
            self.candidates_rejected_not_better += 1
            self.last_decision = "VALID_NOT_BETTER"
            return False
        self._record = ValidatedIncumbent(
            outcome=outcome,
            objective=objective,
            placement_signature=placement_signature(outcome.placements),
            secondary_score=secondary_score,
        )
        self.improvements_accepted += 1
        self.last_decision = "VALID_ACCEPTED"
        return True

    def metadata(self) -> dict[str, object]:
        return {
            "validated_incumbent_available": self._record is not None,
            "validated_incumbent_objective": (
                None if self._record is None else self._record.objective.as_dict()
            ),
            "validated_incumbent_placement_signature": (
                None if self._record is None else self._record.placement_signature
            ),
            "validated_incumbent_secondary_score": (
                None
                if self._record is None or self._record.secondary_score is None
                else self._record.secondary_score.as_dict()
            ),
            "validated_incumbent_candidates_considered": self.candidates_considered,
            "validated_incumbent_candidates_validated": self.candidates_validated,
            "validated_incumbent_rejected_incomplete": (
                self.candidates_rejected_incomplete
            ),
            "validated_incumbent_rejected_not_better": (
                self.candidates_rejected_not_better
            ),
            "validated_incumbent_rejected_invalid": self.candidates_rejected_invalid,
            "validated_incumbent_improvements_accepted": self.improvements_accepted,
        }

    def _is_complete(self, outcome: AlgorithmOutcome) -> bool:
        if outcome.solve.status not in self._SUCCESS_STATUSES:
            return False
        placed_ids = [value.item_id for value in outcome.placements]
        return (
            len(placed_ids) == len(self._required_item_ids)
            and len(set(placed_ids)) == len(placed_ids)
            and frozenset(placed_ids) == self._required_item_ids
        )

    def _objective(self, placements: list[Placement]) -> OfficialObjective:
        used_ids = {value.container_id for value in placements}
        unknown = sorted(used_ids - self._container_costs.keys())
        if unknown:
            raise ValueError(
                "Candidate references unknown container(s): " + ", ".join(unknown)
            )
        return OfficialObjective(
            used_container_count=len(used_ids),
            total_container_cost=sum(self._container_costs[value] for value in used_ids),
        )
