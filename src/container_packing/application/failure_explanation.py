"""Diễn giải failure metadata dùng chung cho CLI và giao diện web."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class FailureExplanation:
    failure_class: str
    title: str
    summary: str
    evidence: tuple[str, ...]
    suggestions: tuple[str, ...]


def explain_failure(
    metadata: Mapping[str, Any], *, language: str = "vi",
) -> FailureExplanation | None:
    """Tạo thông điệp actionable mà không thay đổi kết luận của solver."""
    if language not in {"vi", "en"}:
        raise ValueError(f"Unsupported language: {language!r}")
    status = str(metadata.get("status") or "UNKNOWN")
    validation_valid = metadata.get("validation_valid")
    if status in {"OPTIMAL", "FEASIBLE", "FEASIBLE_TIME_LIMIT"} and validation_valid is not False:
        return None
    failure_class = str(metadata.get("failure_class") or _infer_failure_class(metadata))
    evidence = _evidence(metadata, language)
    vi = language == "vi"

    messages = {
        "INPUT_INVALID": (
            "Dữ liệu đầu vào không hợp lệ", "Input data is invalid",
            "Precheck phát hiện lỗi dữ liệu trước khi chạy thuật toán.",
            "The precheck found invalid input before construction started.",
            ("Sửa dữ liệu theo reason code rồi chạy lại.",),
            ("Correct the reported input issues and run again.",),
        ),
        "ITEM_INCOMPATIBLE": (
            "Có kiện không tương thích với kho", "An item is incompatible with the inventory",
            "Ít nhất một kiện không vừa hoặc vượt payload của mọi container tương thích.",
            "At least one item does not fit, or exceeds every compatible container payload.",
            ("Kiểm tra kích thước, orientation, weight hoặc bổ sung loại container phù hợp.",),
            ("Check dimensions, orientation and weight, or add a compatible container type.",),
        ),
        "CAPACITY_LIMIT_PROVEN": (
            "Giới hạn container chắc chắn không đủ", "The container limit is provably insufficient",
            "Ngay cả capacity aggregate tốt nhất trong giới hạn đã chọn cũng không chứa đủ hàng.",
            "Even the best aggregate capacity within the selected limit is insufficient.",
            ("Tăng số container tối đa ít nhất tới lower bound được báo cáo.",
             "Hoặc giảm số kiện/chọn catalog có volume hay payload lớn hơn."),
            ("Raise the maximum container count to at least the reported lower bound.",
             "Alternatively reduce the items or choose a higher-capacity catalog."),
        ),
        "TIME_LIMIT": (
            "Hết giới hạn thời gian", "Time limit reached",
            "Heuristic chưa tìm được nghiệm complete trong deadline; đây không phải chứng minh vô nghiệm.",
            "The heuristic did not find a complete solution before the deadline; this is not an infeasibility proof.",
            ("Tăng runtime, tăng giới hạn container hoặc dùng Best Fit.",),
            ("Increase runtime or the container limit, or use Best Fit.",),
        ),
        "CANDIDATE_BUDGET_EXHAUSTED": (
            "Đã dùng hết ngân sách candidate", "Candidate budget exhausted",
            "Search đã dùng hết subset/composition/variant được cấu hình mà chưa có nghiệm complete.",
            "Search exhausted its configured subset/composition/variant budget without a complete solution.",
            ("Tăng candidate budget hoặc dùng profile tìm kiếm chuyên sâu hơn.",),
            ("Increase the candidate budget or use a deeper search profile.",),
        ),
        "VALIDATION_FAILED": (
            "Independent validator đã loại nghiệm", "Independent validation rejected the solution",
            "Solver tạo được candidate nhưng nghiệm cuối vi phạm ít nhất một ràng buộc đang hoạt động.",
            "The solver produced a candidate that violates at least one active final constraint.",
            ("Xem validation/violations.csv; không sử dụng objective của candidate này.",),
            ("Inspect validation/violations.csv and do not compare this candidate's objective.",),
        ),
        "HEURISTIC_SEARCH_EXHAUSTED": (
            "Heuristic chưa tìm được nghiệm", "Heuristic search found no solution",
            "Không gian tìm kiếm bounded đã kết thúc mà chưa có nghiệm complete; đây không phải chứng minh vô nghiệm.",
            "The bounded heuristic search ended without a complete solution; this is not an infeasibility proof.",
            ("Tăng container/runtime/candidate budget hoặc đổi item order/thuật toán.",),
            ("Increase containers, runtime or candidate budget, or change ordering/algorithm.",),
        ),
    }
    selected = messages.get(failure_class, messages["HEURISTIC_SEARCH_EXHAUSTED"])
    return FailureExplanation(
        failure_class=failure_class,
        title=selected[0] if vi else selected[1],
        summary=selected[2] if vi else selected[3],
        evidence=evidence,
        suggestions=selected[4] if vi else selected[5],
    )


def _infer_failure_class(metadata: Mapping[str, Any]) -> str:
    status = str(metadata.get("status") or "")
    if status == "INVALID_SOLUTION" or metadata.get("validation_valid") is False:
        return "VALIDATION_FAILED"
    if status == "TIME_LIMIT":
        return "TIME_LIMIT"
    if status == "PRECHECK_FAILED":
        codes = {
            str(value.get("code"))
            for value in metadata.get("hard_precheck_issues", ())
            if isinstance(value, Mapping)
        }
        if any("WITHIN_CONTAINER_LIMIT" in code or "TOTAL_" in code for code in codes):
            return "CAPACITY_LIMIT_PROVEN"
        if codes & {"ITEM_TOO_LARGE", "ITEM_TOO_HEAVY", "NO_ALLOWED_ORIENTATION"}:
            return "ITEM_INCOMPATIBLE"
        return "INPUT_INVALID"
    termination = str(metadata.get("construction_termination_reason") or "")
    if "candidate" in termination or "budget" in termination:
        return "CANDIDATE_BUDGET_EXHAUSTED"
    return "HEURISTIC_SEARCH_EXHAUSTED"


def _evidence(metadata: Mapping[str, Any], language: str) -> tuple[str, ...]:
    vi = language == "vi"
    rows: list[str] = []
    values = (
        ("Số kiện đã xếp tốt nhất" if vi else "Best partial placement count", "best_partial_placement_count"),
        ("Tổng số kiện" if vi else "Total items", "n_items"),
        ("Lower bound container" if vi else "Container lower bound", "container_count_lower_bound"),
        ("Giới hạn container" if vi else "Container limit", "max_used_container_count"),
        ("Candidate subset đã sinh" if vi else "Generated subset candidates", "container_subset_candidates_generated"),
        ("Packing attempts" if vi else "Packing attempts", "packing_attempts"),
        ("Thời gian thuật toán (giây)" if vi else "Algorithm runtime (seconds)", "algorithm_runtime_seconds"),
    )
    for label, key in values:
        value = metadata.get(key)
        if value is not None:
            rows.append(f"{label}: {value}")
    if metadata.get("capacity_limit_required_volume_m3") is not None:
        rows.append(
            ("Volume yêu cầu / đạt được" if vi else "Required / attainable volume")
            + f": {float(metadata['capacity_limit_required_volume_m3']):.3f} / "
            f"{float(metadata.get('capacity_limit_attainable_volume_m3', 0.0)):.3f} m³"
        )
    if metadata.get("capacity_limit_required_payload_kg") is not None:
        rows.append(
            ("Payload yêu cầu / đạt được" if vi else "Required / attainable payload")
            + f": {float(metadata['capacity_limit_required_payload_kg']):.3f} / "
            f"{float(metadata.get('capacity_limit_attainable_payload_kg', 0.0)):.3f} kg"
        )
    reason = metadata.get("construction_termination_reason") or metadata.get(
        "inventory_construction_termination_reason"
    )
    if reason:
        rows.append(("Lý do dừng" if vi else "Termination reason") + f": {reason}")
    raw_issues = metadata.get("hard_precheck_issues") or ()
    for issue in tuple(raw_issues)[:5]:
        if isinstance(issue, Mapping) and issue.get("message"):
            rows.append(
                ("Precheck" if vi else "Precheck")
                + f" [{issue.get('code', 'UNKNOWN')}]: {issue['message']}"
            )
    return tuple(rows)
