from __future__ import annotations

import pandas as pd

from container_packing.web.benchmark_charts import (
    build_quality_gap_figure,
    build_runtime_figure,
    summarize_against_baseline,
)


ALGORITHMS = (
    ("extreme_point_best_fit", "Extreme Point — Best Fit Decreasing"),
    ("extreme_point_ffd", "Extreme Point — First Fit Decreasing"),
    ("maximal_space_best_fit", "Maximal Empty Spaces — Best Fit Decreasing"),
)


def _summary(*, mes_differs: bool = False) -> pd.DataFrame:
    rows = []
    for item_count, gap in ((20, 0.0), (50, 0.0), (100, 1.0)):
        for algorithm, name in ALGORITHMS:
            current = gap
            maximum = gap
            if mes_differs and item_count == 100 and algorithm == "maximal_space_best_fit":
                current = maximum = 2.0
            rows.append({
                "algorithm": algorithm,
                "algorithm_name": name,
                "item_count": item_count,
                "container_gap_lower_bound_median": current,
                "container_gap_lower_bound_min": current,
                "container_gap_lower_bound_max": maximum,
                "case_count": 2,
                "execution_count": 4,
                "runtime_p50_seconds": 2.0 + item_count / 100,
                "runtime_min_seconds": 1.5 + item_count / 100,
                "runtime_max_seconds": 2.5 + item_count / 100,
                "runtime_per_item_p50": (2.0 + item_count / 100) / item_count,
            })
    return pd.DataFrame(rows)


def test_quality_chart_collapses_identical_algorithm_series() -> None:
    figure = build_quality_gap_figure(_summary(), language="vi")

    assert len(figure.data) == 1
    assert figure.data[0].name == "Các thuật toán cùng kết quả tổng hợp"
    assert list(figure.data[0].x) == [20, 50, 100]
    assert list(figure.data[0].y) == [0.0, 0.0, 1.0]
    assert figure.data[0].mode == "markers"
    assert "Số bài mỗi thuật toán" in figure.data[0].hovertemplate


def test_quality_chart_separates_algorithms_only_where_summary_differs() -> None:
    figure = build_quality_gap_figure(_summary(mes_differs=True), language="vi")

    assert len(figure.data) == 4
    assert list(figure.data[0].x) == [20, 50]
    names = {trace.name for trace in figure.data[1:]}
    assert names == {name for _, name in ALGORITHMS}
    assert all(list(trace.x) == [100] for trace in figure.data[1:])


def test_runtime_chart_has_stable_styles_and_unified_hover() -> None:
    figure = build_runtime_figure(_summary(), language="vi")

    assert len(figure.data) == 3
    assert figure.layout.hovermode == "x unified"
    assert figure.layout.yaxis.type == "log"
    assert {trace.line.dash for trace in figure.data} == {"solid", "dash", "dot"}
    assert {trace.marker.symbol for trace in figure.data} == {"circle", "square", "diamond"}
    assert all("Thời gian/kiện" in trace.hovertemplate for trace in figure.data)
    assert all("Số lượt chạy" in trace.hovertemplate for trace in figure.data)


def test_pairwise_conclusion_lists_each_comparator_without_false_winner() -> None:
    outcomes = pd.DataFrame([
        {
            "algorithm_a": "extreme_point_best_fit",
            "algorithm_b": "extreme_point_ffd",
            "outcome_for_a": "TIE",
        },
        {
            "algorithm_a": "extreme_point_best_fit",
            "algorithm_b": "maximal_space_best_fit",
            "outcome_for_a": "TIE",
        },
    ])
    summary, details = summarize_against_baseline(
        outcomes,
        baseline_algorithm="extreme_point_best_fit",
        algorithm_name=dict(ALGORITHMS).__getitem__,
        language="vi",
    )

    assert summary.startswith("Chưa ghi nhận khác biệt")
    assert len(details) == 2
    assert all("0 thắng, 1 hòa, 0 thua" in value for value in details)
    assert "dẫn đầu" not in " ".join([summary, *details]).lower()


def test_quick_conclusion_reports_six_ties_for_each_comparator() -> None:
    rows = []
    for _ in range(6):
        rows.extend([
            {
                "algorithm_a": "extreme_point_best_fit",
                "algorithm_b": "extreme_point_ffd",
                "outcome_for_a": "TIE",
            },
            {
                "algorithm_a": "extreme_point_best_fit",
                "algorithm_b": "maximal_space_best_fit",
                "outcome_for_a": "TIE",
            },
        ])
    _, details = summarize_against_baseline(
        pd.DataFrame(rows),
        baseline_algorithm="extreme_point_best_fit",
        algorithm_name=dict(ALGORITHMS).__getitem__,
        language="vi",
    )

    assert len(details) == 2
    assert all("0 thắng, 6 hòa, 0 thua" in value for value in details)
