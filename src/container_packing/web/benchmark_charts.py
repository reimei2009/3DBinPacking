"""Biểu đồ benchmark dễ diễn giải, không chứa logic Streamlit."""

from __future__ import annotations

from collections.abc import Callable

import pandas as pd
import plotly.graph_objects as go


_ALGORITHM_STYLES = {
    "extreme_point_best_fit": {"color": "#72B7F2", "dash": "solid", "symbol": "circle"},
    "extreme_point_ffd": {"color": "#0068C9", "dash": "dash", "symbol": "square"},
    "maximal_space_best_fit": {"color": "#FF9DA7", "dash": "dot", "symbol": "diamond"},
}
_FALLBACK_STYLES = (
    {"color": "#54A24B", "dash": "dashdot", "symbol": "triangle-up"},
    {"color": "#ECA82C", "dash": "longdash", "symbol": "cross"},
)


def _style(algorithm: str, fallback_index: int) -> dict[str, object]:
    return _ALGORITHM_STYLES.get(
        algorithm, _FALLBACK_STYLES[fallback_index % len(_FALLBACK_STYLES)],
    )


def _number(value: object) -> float | None:
    numeric = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    return None if pd.isna(numeric) else float(numeric)


def _same_summary(values: pd.DataFrame) -> bool:
    """True khi median và min-max giống nhau ở một quy mô."""
    if len(values) < 2:
        return False
    signatures = set()
    for row in values.itertuples(index=False):
        signatures.add(tuple(
            None if value is None else round(value, 12)
            for value in (
                _number(getattr(row, "container_gap_lower_bound_median", None)),
                _number(getattr(row, "container_gap_lower_bound_min", None)),
                _number(getattr(row, "container_gap_lower_bound_max", None)),
            )
        ))
    return len(signatures) == 1


def build_quality_gap_figure(
    summary: pd.DataFrame,
    *,
    language: str = "vi",
) -> go.Figure:
    """Dựng điểm chất lượng; các series trùng nhau được biểu diễn như một kết quả hòa."""
    frame = summary.copy()
    required = {
        "algorithm", "algorithm_name", "item_count",
        "container_gap_lower_bound_median",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Quality chart is missing: {', '.join(sorted(missing))}")
    for column in (
        "container_gap_lower_bound_median", "container_gap_lower_bound_min",
        "container_gap_lower_bound_max", "case_count",
    ):
        if column not in frame:
            frame[column] = pd.NA
    frame = frame[frame["container_gap_lower_bound_median"].notna()].copy()
    figure = go.Figure()
    tied_rows: list[dict[str, object]] = []
    separate_rows: list[pd.DataFrame] = []
    for item_count, values in frame.groupby("item_count", sort=True, dropna=False):
        values = values.sort_values("algorithm", kind="stable")
        if _same_summary(values):
            first = values.iloc[0]
            tied_rows.append({
                "item_count": item_count,
                "median": first["container_gap_lower_bound_median"],
                "minimum": first["container_gap_lower_bound_min"],
                "maximum": first["container_gap_lower_bound_max"],
                "algorithms": "<br>".join(values["algorithm_name"].astype(str)),
                "case_count": int(pd.to_numeric(values["case_count"], errors="coerce").max())
                if pd.to_numeric(values["case_count"], errors="coerce").notna().any() else None,
            })
        else:
            separate_rows.append(values)

    if tied_rows:
        tied = pd.DataFrame(tied_rows).sort_values("item_count")
        custom = tied[["algorithms", "minimum", "maximum", "case_count"]].to_numpy()
        figure.add_trace(go.Scatter(
            x=tied["item_count"], y=tied["median"], mode="markers",
            name=("Các thuật toán cùng kết quả tổng hợp" if language == "vi"
                  else "Algorithms share the same summary"),
            marker={
                "color": "#A0A7B4", "size": 14, "symbol": "diamond",
                "line": {"color": "#FFFFFF", "width": 1.5},
            },
            customdata=custom,
            hovertemplate=(
                "<b>Cùng kết quả tổng hợp</b><br>Số kiện: %{x}<br>"
                "Gap trung vị: %{y:.2f}<br>Khoảng nhỏ nhất–lớn nhất: %{customdata[1]:.2f}–%{customdata[2]:.2f}<br>"
                "Số bài mỗi thuật toán: %{customdata[3]}<br><br>%{customdata[0]}<extra></extra>"
                if language == "vi" else
                "<b>Same aggregate result</b><br>Items: %{x}<br>Median gap: %{y:.2f}<br>"
                "Minimum–maximum: %{customdata[1]:.2f}–%{customdata[2]:.2f}<br>"
                "Cases per algorithm: %{customdata[3]}<br><br>%{customdata[0]}<extra></extra>"
            ),
        ))

    separate = pd.concat(separate_rows, ignore_index=True) if separate_rows else pd.DataFrame()
    if not separate.empty:
        for index, (algorithm, values) in enumerate(separate.groupby("algorithm", sort=True)):
            values = values.sort_values("item_count")
            style = _style(str(algorithm), index)
            minimum = pd.to_numeric(values["container_gap_lower_bound_min"], errors="coerce")
            maximum = pd.to_numeric(values["container_gap_lower_bound_max"], errors="coerce")
            median = pd.to_numeric(values["container_gap_lower_bound_median"], errors="coerce")
            custom = pd.DataFrame({
                "minimum": minimum,
                "maximum": maximum,
                "case_count": pd.to_numeric(values["case_count"], errors="coerce"),
            }).to_numpy()
            figure.add_trace(go.Scatter(
                x=values["item_count"], y=median, mode="markers",
                name=str(values["algorithm_name"].iloc[0]),
                marker={
                    "color": style["color"], "size": 12, "symbol": style["symbol"],
                    "line": {"color": "#FFFFFF", "width": 1.2},
                },
                error_y={
                    "type": "data", "symmetric": False,
                    "array": (maximum - median).fillna(0),
                    "arrayminus": (median - minimum).fillna(0),
                    "visible": True,
                },
                customdata=custom,
                hovertemplate=(
                    "<b>%{fullData.name}</b><br>Số kiện: %{x}<br>Gap trung vị: %{y:.2f}<br>"
                    "Khoảng nhỏ nhất–lớn nhất: %{customdata[0]:.2f}–%{customdata[1]:.2f}<br>"
                    "Số bài: %{customdata[2]}<extra></extra>"
                    if language == "vi" else
                    "<b>%{fullData.name}</b><br>Items: %{x}<br>Median gap: %{y:.2f}<br>"
                    "Minimum–maximum: %{customdata[0]:.2f}–%{customdata[1]:.2f}<br>"
                    "Cases: %{customdata[2]}<extra></extra>"
                ),
            ))

    figure.update_layout(
        title="Chất lượng nghiệm theo quy mô" if language == "vi" else "Quality by scale",
        xaxis_title="Số kiện" if language == "vi" else "Items",
        yaxis_title=("Số container nhiều hơn cận tối thiểu sơ bộ" if language == "vi"
                     else "Containers above the preliminary lower bound"),
        hovermode="closest", legend_title_text="Thuật toán" if language == "vi" else "Algorithm",
        margin={"l": 20, "r": 20, "t": 60, "b": 20},
    )
    return figure


def build_runtime_figure(
    summary: pd.DataFrame,
    *,
    language: str = "vi",
) -> go.Figure:
    """Dựng xu hướng wall runtime với tooltip thống nhất theo quy mô."""
    frame = summary.copy()
    required = {
        "algorithm", "algorithm_name", "item_count", "runtime_p50_seconds",
        "runtime_min_seconds", "runtime_max_seconds", "execution_count",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Runtime chart is missing: {', '.join(sorted(missing))}")
    if "runtime_per_item_p50" not in frame:
        frame["runtime_per_item_p50"] = (
            pd.to_numeric(frame["runtime_p50_seconds"], errors="coerce")
            / pd.to_numeric(frame["item_count"], errors="coerce")
        )
    figure = go.Figure()
    for index, (algorithm, values) in enumerate(frame.groupby("algorithm", sort=True)):
        values = values.sort_values("item_count")
        style = _style(str(algorithm), index)
        median = pd.to_numeric(values["runtime_p50_seconds"], errors="coerce")
        minimum = pd.to_numeric(values["runtime_min_seconds"], errors="coerce")
        maximum = pd.to_numeric(values["runtime_max_seconds"], errors="coerce")
        custom = values[[
            "runtime_min_seconds", "runtime_max_seconds", "runtime_per_item_p50",
            "execution_count",
        ]].to_numpy()
        figure.add_trace(go.Scatter(
            x=values["item_count"], y=median, mode="lines+markers",
            name=str(values["algorithm_name"].iloc[0]),
            line={"color": style["color"], "dash": style["dash"], "width": 3},
            marker={
                "color": style["color"], "symbol": style["symbol"], "size": 9,
                "line": {"color": "#FFFFFF", "width": 1},
            },
            error_y={
                "type": "data", "symmetric": False,
                "array": (maximum - median).fillna(0),
                "arrayminus": (median - minimum).fillna(0),
                "visible": True,
            },
            customdata=custom,
            hovertemplate=(
                "Thời gian thường gặp: %{y:.3f} giây<br>"
                "Nhanh nhất–chậm nhất: %{customdata[0]:.3f}–%{customdata[1]:.3f} giây<br>"
                "Thời gian/kiện: %{customdata[2]:.4f} giây<br>Số lượt chạy: %{customdata[3]}<extra></extra>"
                if language == "vi" else
                "Typical runtime: %{y:.3f} seconds<br>"
                "Fastest–slowest: %{customdata[0]:.3f}–%{customdata[1]:.3f} seconds<br>"
                "Runtime/item: %{customdata[2]:.4f} seconds<br>Executions: %{customdata[3]}<extra></extra>"
            ),
        ))
    figure.update_layout(
        title=("Thời gian toàn quy trình theo quy mô" if language == "vi"
               else "End-to-end runtime by scale"),
        xaxis_title="Số kiện" if language == "vi" else "Items",
        yaxis_title=("Thời gian toàn quy trình thường gặp (giây)" if language == "vi"
                     else "Typical end-to-end runtime (seconds)"),
        yaxis_type="log", hovermode="x unified",
        legend_title_text="Thuật toán" if language == "vi" else "Algorithm",
        margin={"l": 20, "r": 20, "t": 60, "b": 20},
    )
    figure.update_xaxes(
        showspikes=True, spikemode="across", spikesnap="cursor",
        spikedash="dot", spikethickness=1,
    )
    return figure


def summarize_against_baseline(
    outcomes: pd.DataFrame,
    *,
    baseline_algorithm: str,
    algorithm_name: Callable[[str], str],
    language: str = "vi",
) -> tuple[str, list[str]]:
    """Tạo kết luận nghiệp vụ riêng cho từng comparator."""
    records: dict[str, list[str]] = {}
    for row in outcomes.itertuples(index=False):
        left, right = str(row.algorithm_a), str(row.algorithm_b)
        outcome = str(row.outcome_for_a)
        if left == baseline_algorithm and right != baseline_algorithm:
            comparator = right
            comparator_outcome = {"WIN": "LOSS", "LOSS": "WIN"}.get(outcome, outcome)
        elif right == baseline_algorithm and left != baseline_algorithm:
            comparator = left
            comparator_outcome = outcome
        else:
            continue
        records.setdefault(comparator, []).append(comparator_outcome)

    if not records:
        summary = "Chưa đủ dữ liệu so sánh ghép cặp." if language == "vi" else "Insufficient paired evidence."
        return summary, []
    details: list[str] = []
    all_tied = True
    for comparator in sorted(records):
        values = records[comparator]
        wins, ties, losses = values.count("WIN"), values.count("TIE"), values.count("LOSS")
        all_tied = all_tied and ties == len(values)
        name = algorithm_name(comparator)
        if language == "vi":
            details.append(
                f"{name}: {wins} thắng, {ties} hòa, {losses} thua so với {algorithm_name(baseline_algorithm)}."
            )
        else:
            details.append(
                f"{name}: {wins} wins, {ties} ties and {losses} losses versus {algorithm_name(baseline_algorithm)}."
            )
    if all_tied:
        summary = (
            "Chưa ghi nhận khác biệt về số container hoặc chi phí trên các bài đã so sánh."
            if language == "vi" else
            "No difference in container count or cost was observed in the compared cases."
        )
    else:
        summary = (
            "Kết quả chất lượng khác nhau giữa các thuật toán; xem từng comparator bên dưới."
            if language == "vi" else
            "Quality results vary by algorithm; see each comparator below."
        )
    return summary, details
