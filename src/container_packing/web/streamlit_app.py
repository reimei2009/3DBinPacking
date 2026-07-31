"""Thin Streamlit research UI; all optimization remains in the core package."""

from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import tempfile
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from container_packing.algorithms.registry import get_algorithm, list_algorithms
from container_packing.application.service import (
    build_experiment_request,
    discover_benchmark_runs,
    discover_runs,
    execute_benchmark_comparison,
    execute_experiment,
    get_instance_limits,
    resolve_result_run_dir,
)
from container_packing.data_loader import load_config
from container_packing.levels.registry import get_level, list_levels
from container_packing.levels.level_08_routing import load_delivery_stops
from container_packing.instance_data import ITEM_SELECTION_STRATEGIES
from container_packing.runtime.project import find_project_root
from container_packing.visualization.plotly_3d import (
    DEFAULT_DIMMED_OPACITY,
    DEFAULT_ITEM_OPACITY,
    create_figure,
)
from container_packing.visualization.scene_schema import load_scene
from container_packing.web.i18n import algorithm_family, text as t

OPACITY_PRESETS = {"solid": DEFAULT_ITEM_OPACITY, "balanced": 0.75, "xray": 0.30}


def _level8_web_profiles(root: Path) -> dict[str, dict[str, Any]]:
    payload = load_config(root / "config/level_08/web_profiles.yaml")
    profiles = payload.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError("Level 8 web profile registry is empty")
    return {str(key): dict(value) for key, value in profiles.items()}


def _snapshot_uploaded_stops(uploaded: Any) -> Path:
    """Persist one uploaded CSV outside the source tree until the run snapshots it."""
    content = uploaded.getvalue()
    checksum = hashlib.sha256(content).hexdigest()
    destination = (
        Path(tempfile.gettempdir())
        / "3d-container-packing"
        / "route-uploads"
        / f"{checksum}.csv"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        destination.write_bytes(content)
    return destination


def _exact_reference_item_limit(algorithm_id: str, config: dict[str, Any]) -> int | None:
    """Read an optional exact-reference cap from the selected algorithm config."""
    if algorithm_id != "milp_big_m":
        return None
    value = config.get("solver", {}).get("orientation_reference_max_items")
    return None if value is None else int(value)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _localized_frame(frame: pd.DataFrame, language: str, kind: str) -> pd.DataFrame:
    if language == "en":
        return frame
    mappings = {
        "containers": {
            "container_id": "Mã container", "used": "Đã dùng", "item_count": "Số kiện",
            "loaded_weight_kg": "Khối lượng đã xếp (kg)", "max_weight_kg": "Tải trọng tối đa (kg)",
            "weight_utilization_pct": "Sử dụng tải trọng (%)", "loaded_volume_m3": "Thể tích đã xếp (m³)",
            "container_volume_m3": "Thể tích container (m³)", "volume_utilization_pct": "Sử dụng thể tích (%)",
            "cost": "Chi phí thực nghiệm",
        },
        "placements": {
            "item_id": "Mã kiện", "container_id": "Mã container",
            "x_mm": "X (mm)", "y_mm": "Y (mm)", "z_mm": "Z (mm)",
            "length_mm": "Dài (mm)", "width_mm": "Rộng (mm)", "height_mm": "Cao (mm)",
            "weight_kg": "Khối lượng (kg)", "volume_m3": "Thể tích (m³)",
        },
    }
    return frame.rename(columns=mappings[kind])


def _scene_items(scene: dict[str, Any], container_id: str | None) -> list[tuple[str, dict[str, Any]]]:
    return [
        (container["container_id"], item)
        for container in scene["containers"]
        if container_id is None or container["container_id"] == container_id
        for item in container["items"]
    ]


def _render_selected_item(container_id: str, item: dict[str, Any], language: str) -> None:
    st.markdown(f"**{t('selected_details', language)}**")
    position = item["position_mm"]
    dimensions = item["dimensions_mm"]
    values = (
        (t("items_metric", language), item["item_id"]),
        ("Container", container_id),
        (t("position", language), f"({position['x']:g}, {position['y']:g}, {position['z']:g}) mm"),
        (t("dimensions", language), f"{dimensions['length']:g} × {dimensions['width']:g} × {dimensions['height']:g} mm"),
        (t("weight", language), f"{item.get('weight_kg', 0):g} kg"),
    )
    for column, (label, value) in zip(st.columns(len(values)), values):
        column.metric(label, value)


def _algorithm_parameters(algorithm_id: str, defaults: dict[str, Any], language: str) -> dict[str, Any]:
    parameters: dict[str, Any] = {}
    if algorithm_id == "milp_big_m":
        parameters["time_limit_seconds"] = st.sidebar.number_input(
            t("time_limit", language), min_value=1, value=int(defaults.get("time_limit_seconds", 600)), step=1,
            key="time_limit_seconds",
        )
        parameters["mip_rel_gap"] = st.sidebar.number_input(
            t("mip_gap", language), min_value=0.0, max_value=1.0,
            value=float(defaults.get("mip_rel_gap", 0.0)), step=0.001, format="%.4f", key="mip_rel_gap",
        )
    else:
        parameters["subset_enumeration_limit"] = st.sidebar.number_input(
            t("subset_limit", language), min_value=1,
            value=int(defaults.get("subset_enumeration_limit", 12)), step=1, key="subset_enumeration_limit",
        )
    if algorithm_id == "extreme_point_hill_climbing":
        parameters["max_iterations"] = st.sidebar.number_input(
            t("hill_iterations", language), min_value=0, value=int(defaults.get("max_iterations", 10)), step=1,
            key="max_iterations",
        )
        parameters["max_neighbors"] = st.sidebar.number_input(
            t("neighbors", language), min_value=1, value=int(defaults.get("max_neighbors", 24)), step=1,
            key="max_neighbors",
        )
    if algorithm_id == "extreme_point_simulated_annealing":
        parameters["max_iterations"] = st.sidebar.number_input(
            t("annealing_iterations", language), min_value=0, value=int(defaults.get("max_iterations", 200)), step=10,
            key="max_iterations",
        )
        parameters["initial_temperature"] = st.sidebar.number_input(
            t("temperature", language), min_value=0.0001,
            value=float(defaults.get("initial_temperature", 0.25)), step=0.01, format="%.4f", key="initial_temperature",
        )
        parameters["cooling_rate"] = st.sidebar.number_input(
            t("cooling", language), min_value=0.0001, max_value=0.9999,
            value=float(defaults.get("cooling_rate", 0.97)), step=0.001, format="%.4f", key="cooling_rate",
        )
    return parameters


def _level_config_overrides(level_id: str, config: dict[str, Any], language: str) -> dict[str, Any]:
    """Render level-owned settings and persist them with the immutable run."""
    if level_id not in {"level_02", "level_03", "level_04", "level_05"}:
        return {}
    support = config["support"]
    threshold = st.sidebar.number_input(
        t("support_threshold", language),
        min_value=0.01,
        max_value=1.00,
        value=float(support["threshold"]),
        step=0.01,
        format="%.2f",
        help=t("support_threshold_help", language),
        key=f"{level_id}_support_threshold",
    )
    st.sidebar.caption(t("base_center_support_enabled", language))
    return {"support": {"threshold": float(threshold)}}


def _render_level_contract(level_id: str, language: str) -> None:
    level = get_level(level_id)
    contract = level.contract
    st.subheader(contract.title.resolve(language))
    st.markdown(f"### {t('problem', language)}")
    st.write(contract.problem.resolve(language))
    st.info(t("milp_note", language))
    st.markdown(f"### {t('notation', language)}")
    for expression in contract.notation:
        st.markdown(f"**{expression.title.resolve(language)}**")
        st.latex(expression.latex)
        st.write(expression.explanation.resolve(language))
        st.caption(f"{t('code_mapping', language)}: `{expression.code_mapping}`")
    st.markdown(f"### {t('objective', language)}")
    st.latex(contract.objective.latex)
    st.write(contract.objective.explanation.resolve(language))
    st.caption(f"{t('code_mapping', language)}: `{contract.objective.code_mapping}`")
    st.markdown(f"### {t('variables', language)}")
    for variable in contract.variables:
        with st.expander(f"{variable.symbol} — {variable.meaning.resolve(language)}"):
            st.latex(variable.latex)
            st.write(f"**{variable.variable_type.resolve(language)}** · {variable.indices.resolve(language)}")
            st.write(variable.meaning.resolve(language))
            st.caption(f"{t('code_mapping', language)}: `{variable.code_mapping}`")
    st.markdown(f"### {t('constraints', language)}")
    for constraint in contract.active_constraints:
        with st.expander(f"{constraint.constraint_id} — {constraint.name.resolve(language)}"):
            st.latex(constraint.latex)
            st.write(constraint.meaning.resolve(language))
            st.caption(f"{t('code_mapping', language)}: `{constraint.code_mapping}`")
    left, right = st.columns(2)
    with left:
        st.markdown(f"**{t('assumptions', language)}**")
        for value in contract.assumptions:
            st.write(f"- {value.resolve(language)}")
    with right:
        st.markdown(f"**{t('inactive', language)}**")
        st.write(", ".join(value.resolve(language) for value in contract.inactive_constraints))
    st.warning(" ".join(value.resolve(language) for value in contract.limitations))
    st.success(contract.solution_claim.resolve(language))


def _render_run(run_dir: Path, language: str) -> None:
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        st.error(f"Không tìm thấy manifest: {manifest_path}" if language == "vi" else f"Missing manifest: {manifest_path}")
        return
    manifest = _read_json(manifest_path)
    metrics_path = run_dir / "metrics" / "metrics.json"
    metrics = _read_json(metrics_path) if metrics_path.is_file() else {}
    st.caption(str(run_dir))
    columns = st.columns(6)
    values = (
        (t("status", language), manifest.get("status", "unknown")),
        (t("validation", language), manifest.get("validation_status", "unknown")),
        (t("items_metric", language), metrics.get("n_items", "—")),
        (t("containers_used", language), metrics.get("container_count", "—")),
        (t("objective_metric", language), metrics.get("objective_value", "—")),
        (t("runtime", language), f"{float(metrics.get('algorithm_runtime_seconds', 0)):.3f}"),
    )
    for column, (label, value) in zip(columns, values):
        column.metric(label, value)
    replay_status = metrics.get("sequential_simulation_status")
    if replay_status and replay_status != "DISABLED":
        replay_runtime = metrics.get("sequential_replay_total_runtime_seconds")
        checked_states = metrics.get("sequential_replay_states_checked")
        reason = metrics.get("sequential_simulation_skip_reason") or metrics.get(
            "sequential_replay_termination_reason"
        )
        replay_text = (
            f"Replay tuần tự: {replay_status}"
            + (f" · {float(replay_runtime):.3f}s" if replay_runtime is not None else "")
            + (f" · {checked_states} trạng thái" if checked_states is not None else "")
            + (f" · {reason}" if reason else "")
        ) if language == "vi" else (
            f"Sequential replay: {replay_status}"
            + (f" · {float(replay_runtime):.3f}s" if replay_runtime is not None else "")
            + (f" · {checked_states} states" if checked_states is not None else "")
            + (f" · {reason}" if reason else "")
        )
        if replay_status == "VALID":
            st.success(replay_text)
        elif replay_status == "REPLAY_TIME_LIMIT":
            st.warning(replay_text)
        else:
            st.error(replay_text)
    scene_path = run_dir / "visualization" / "scene.json"
    if not scene_path.is_file():
        st.warning(t("no_scene", language))
        return
    scene = load_scene(scene_path)
    st.warning(scene.get("warnings", {}).get(language, scene["warning"]))
    container_ids = [value["container_id"] for value in scene["containers"]]
    all_containers = t("all_containers", language)
    mode_key = f"display-mode-{run_dir.name}"
    opacity_key = f"item-opacity-{run_dir.name}"

    def apply_opacity_preset() -> None:
        st.session_state[opacity_key] = OPACITY_PRESETS[st.session_state[mode_key]]

    if opacity_key not in st.session_state:
        st.session_state[opacity_key] = DEFAULT_ITEM_OPACITY
    with st.expander(t("display_controls", language), expanded=True):
        primary = st.columns(4)
        selected_view = primary[0].selectbox(
            t("view", language), [*container_ids, all_containers], key=f"view-{run_dir.name}"
        )
        primary[1].selectbox(
            t("display_mode", language), tuple(OPACITY_PRESETS),
            format_func=lambda value: t(f"mode_{value}", language), key=mode_key,
            on_change=apply_opacity_preset,
        )
        opacity = primary[2].slider(
            t("opacity", language), min_value=0.20, max_value=1.00, step=0.01, key=opacity_key,
        )
        color_mode = primary[3].selectbox(
            "Màu theo" if language == "vi" else "Color by",
            ("item", "delivery_stop") if scene.get("level") == "level_08" else ("item",),
            format_func=lambda value: (
                "Điểm giao" if language == "vi" and value == "delivery_stop"
                else "Kiện hàng" if language == "vi"
                else "Delivery stop" if value == "delivery_stop"
                else "Item"
            ),
            key=f"color-mode-{run_dir.name}",
        )
        selected_container = None if selected_view == all_containers else selected_view
        available_items = _scene_items(scene, selected_container)
        item_ids = [item["item_id"] for _, item in available_items]
        secondary = st.columns(2)
        selected_item_id = secondary[0].selectbox(
            t("selected_item", language), ["", *item_ids],
            format_func=lambda value: t("no_selection", language) if value == "" else value,
            key=f"selected-item-{run_dir.name}",
        ) or None
        hidden_item_ids = set(secondary[1].multiselect(
            t("hidden_items", language), item_ids, key=f"hidden-items-{run_dir.name}",
        ))
        visibility = st.columns(2)
        labels = visibility[0].checkbox(t("show_labels", language), value=False, key=f"labels-{run_dir.name}")
        boundaries = visibility[1].checkbox(t("show_boundaries", language), value=True, key=f"bounds-{run_dir.name}")
    if selected_item_id is not None:
        hidden_item_ids.discard(selected_item_id)
    figure = create_figure(
        scene,
        container_id=selected_container,
        show_labels=labels,
        show_boundaries=boundaries,
        language=language,
        item_opacity=float(opacity),
        selected_item_id=selected_item_id,
        dimmed_opacity=DEFAULT_DIMMED_OPACITY,
        hidden_item_ids=hidden_item_ids,
        item_color_mode=color_mode,
    )
    st.plotly_chart(figure, width="stretch", config={"displaylogo": False, "scrollZoom": True})
    if selected_item_id is not None:
        selected_container_id, selected_item = next(
            value for value in available_items if value[1]["item_id"] == selected_item_id
        )
        _render_selected_item(selected_container_id, selected_item, language)
    summary_path = run_dir / "solution" / "containers.csv"
    placements_path = run_dir / "solution" / "placements.csv"
    if summary_path.is_file():
        st.markdown(f"**{t('utilization', language)}**")
        st.dataframe(_localized_frame(pd.read_csv(summary_path), language, "containers"), hide_index=True, width="stretch")
    if placements_path.is_file():
        with st.expander(t("placements", language)):
            st.dataframe(_localized_frame(pd.read_csv(placements_path), language, "placements"), hide_index=True, width="stretch")
    support_path = run_dir / "solution" / "support.csv"
    if support_path.is_file():
        with st.expander("Hỗ trợ đáy" if language == "vi" else "Base support"):
            st.dataframe(pd.read_csv(support_path), hide_index=True, width="stretch")


    _render_logistics_route(run_dir, language)
    _render_sequential_replay(run_dir, scene, language)


def _routing_artifacts(
    run_dir: Path,
) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame] | None:
    routing = run_dir / "routing"
    route_path = routing / "route.json"
    stops_path = routing / "delivery_stops.csv"
    legs_path = routing / "route_legs.csv"
    if not route_path.is_file() or not stops_path.is_file() or not legs_path.is_file():
        return None
    return _read_json(route_path), pd.read_csv(stops_path), pd.read_csv(legs_path)


def _route_figure(
    route: dict[str, Any],
    stops: pd.DataFrame,
    *,
    highlighted_stop_id: str | None = None,
) -> go.Figure:
    coordinates = route.get("polyline_coordinates", [])
    figure = go.Figure()
    if coordinates:
        figure.add_trace(
            go.Scattermap(
                lat=[value["latitude"] for value in coordinates],
                lon=[value["longitude"] for value in coordinates],
                mode="lines",
                line={"width": 4, "color": "#e45756"},
                name="Route",
            )
        )
    labels: list[str] = []
    colors: list[str] = []
    sizes: list[int] = []
    for row in stops.itertuples(index=False):
        priority = getattr(row, "delivery_priority", "")
        labels.append(
            "Depot"
            if str(row.stop_type) == "depot"
            else f"{priority} · {row.stop_id}"
        )
        selected = highlighted_stop_id == str(row.stop_id)
        colors.append(
            "#ffcc00"
            if selected
            else "#111827"
            if str(row.stop_type) == "depot"
            else "#2563eb"
        )
        sizes.append(20 if selected else 15)
    figure.add_trace(
        go.Scattermap(
            lat=stops["latitude"].astype(float),
            lon=stops["longitude"].astype(float),
            mode="markers+text",
            text=labels,
            textposition="top right",
            marker={"size": sizes, "color": colors},
            customdata=stops[["stop_id", "name"]].values,
            hovertemplate="<b>%{customdata[0]}</b><br>%{customdata[1]}<extra></extra>",
            name="Stops",
        )
    )
    figure.update_layout(
        map={"style": "open-street-map", "zoom": 10},
        margin={"l": 0, "r": 0, "t": 20, "b": 0},
        height=450,
        showlegend=False,
    )
    return figure


def _render_google_route_map(
    route: dict[str, Any],
    stops: pd.DataFrame,
    browser_key: str,
    *,
    highlighted_stop_id: str | None = None,
) -> None:
    """Use only the separately restricted browser key in client-side HTML."""
    payload = {
        "route": route.get("polyline_coordinates", []),
        "stops": stops.to_dict(orient="records"),
        "highlighted": highlighted_stop_id,
    }
    html = f"""
    <div id="route-map" style="height:450px;width:100%;border-radius:8px"></div>
    <script>
      const DATA = {json.dumps(payload, ensure_ascii=False)};
      function initMap() {{
        const first = DATA.stops[0];
        const map = new google.maps.Map(document.getElementById("route-map"), {{
          center: {{lat:Number(first.latitude), lng:Number(first.longitude)}},
          zoom: 11,
          mapTypeControl: false
        }});
        const path = DATA.route.map(p => ({{lat:Number(p.latitude), lng:Number(p.longitude)}}));
        new google.maps.Polyline({{path, map, strokeColor:"#e45756", strokeWeight:4}});
        DATA.stops.forEach(stop => {{
          const selected = stop.stop_id === DATA.highlighted;
          new google.maps.Marker({{
            map,
            position: {{lat:Number(stop.latitude), lng:Number(stop.longitude)}},
            title: `${{stop.stop_id}} · ${{stop.name}}`,
            label: stop.stop_type === "depot" ? "D" : String(stop.delivery_priority),
            zIndex: selected ? 100 : 1
          }});
        }});
      }}
    </script>
    <script async src="https://maps.googleapis.com/maps/api/js?key={browser_key}&callback=initMap"></script>
    """
    components.html(html, height=470)


def _render_logistics_route(
    run_dir: Path,
    language: str,
    *,
    highlighted_stop_id: str | None = None,
    compact: bool = False,
) -> None:
    artifacts = _routing_artifacts(run_dir)
    if artifacts is None:
        return
    route, stops, legs = artifacts
    if not compact:
        st.markdown(
            "### Bản đồ giao hàng nhiều điểm"
            if language == "vi"
            else "### Multi-stop delivery map"
        )
    columns = st.columns(4)
    columns[0].metric("Provider", str(route.get("provider_used", "unknown")))
    columns[1].metric(
        "Stops", int((stops["stop_type"].astype(str) == "delivery").sum())
    )
    columns[2].metric(
        "Distance",
        f"{float(route.get('total_distance_meters', 0.0)) / 1000.0:.2f} km",
    )
    columns[3].metric(
        "Duration",
        f"{float(route.get('total_duration_seconds', 0.0)) / 60.0:.1f} min",
    )
    if route.get("warning"):
        st.warning(str(route["warning"]))
    browser_key = os.environ.get("GOOGLE_MAPS_BROWSER_KEY", "").strip()
    if browser_key and route.get("provider_used") == "google_routes":
        _render_google_route_map(
            route,
            stops,
            browser_key,
            highlighted_stop_id=highlighted_stop_id,
        )
    else:
        st.plotly_chart(
            _route_figure(
                route, stops, highlighted_stop_id=highlighted_stop_id
            ),
            width="stretch",
            config={"displaylogo": False},
            key=(
                f"route-map-{run_dir.name}-"
                f"{'replay' if compact else 'overview'}-"
                f"{highlighted_stop_id or 'all'}"
            ),
        )
    if not compact:
        item_snapshot = run_dir / "input_snapshot" / "items.csv"
        counts: dict[str, int] = {}
        if item_snapshot.is_file():
            item_frame = pd.read_csv(item_snapshot)
            if "delivery_stop_id" in item_frame:
                counts = (
                    item_frame["delivery_stop_id"]
                    .astype(str)
                    .value_counts()
                    .to_dict()
                )
        delivery_rows = stops[
            stops["stop_type"].astype(str) == "delivery"
        ].copy()
        delivery_rows["item_count"] = (
            delivery_rows["stop_id"].astype(str).map(counts).fillna(0).astype(int)
        )
        with st.expander(
            "Các chặng và điểm giao"
            if language == "vi"
            else "Route legs and stops"
        ):
            st.dataframe(delivery_rows, hide_index=True, width="stretch")
            st.dataframe(legs, hide_index=True, width="stretch")


@st.fragment(run_every=0.5)
def _render_sequential_replay(
    run_dir: Path, scene: dict[str, Any], language: str
) -> None:
    """Render persisted replay evidence without executing simulation logic."""
    simulation_dir = run_dir / "simulation"
    events_path = simulation_dir / "events.jsonl"
    metrics_path = simulation_dir / "simulation_metrics.json"
    if not events_path.is_file() or not metrics_path.is_file():
        return
    try:
        events = [
            json.loads(line)
            for line in events_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        metrics = _read_json(metrics_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        prefix = "Không thể đọc artifact mô phỏng: " if language == "vi" else "Cannot read replay artifacts: "
        st.error(prefix + str(exc))
        return
    if not events:
        return
    st.markdown(
        "### Mô phỏng bốc dỡ tuần tự"
        if language == "vi"
        else "### Sequential loading/unloading replay"
    )
    st.warning(
        (
            "Đây là replay offline xác định từ artifact đã kiểm định; chưa mô phỏng "
            "thiết bị nâng, không gian staging, tuyến đường hoặc thời gian thực."
        )
        if language == "vi"
        else (
            "This is a deterministic offline replay of validated artifacts; it does "
            "not model handling equipment, staging space, routing, or real time."
        )
    )
    index_key = f"sequential-event-{run_dir.name}"
    playing_key = f"sequential-playing-{run_dir.name}"
    speed_key = f"sequential-speed-{run_dir.name}"
    accumulator_key = f"sequential-accumulator-{run_dir.name}"
    st.session_state.setdefault(index_key, 0)
    st.session_state.setdefault(playing_key, False)
    st.session_state.setdefault(accumulator_key, 0.0)
    controls = st.columns((1, 1, 1, 2))
    if controls[0].button(
        "⏮", key=f"sequential-previous-{run_dir.name}", help="Previous"
    ):
        st.session_state[index_key] = max(
            0, int(st.session_state[index_key]) - 1
        )
        st.session_state[playing_key] = False
    if controls[1].button(
        "⏸" if st.session_state[playing_key] else "▶",
        key=f"sequential-play-{run_dir.name}",
        help="Play / pause",
    ):
        st.session_state[playing_key] = not bool(st.session_state[playing_key])
    if controls[2].button(
        "⏭", key=f"sequential-next-{run_dir.name}", help="Next"
    ):
        st.session_state[index_key] = min(
            len(events) - 1, int(st.session_state[index_key]) + 1
        )
        st.session_state[playing_key] = False
    speed = controls[3].selectbox(
        "Tốc độ" if language == "vi" else "Speed",
        (0.5, 1.0, 2.0),
        format_func=lambda value: f"{value:g}×",
        key=speed_key,
    )
    if st.session_state[playing_key]:
        st.session_state[accumulator_key] = (
            float(st.session_state[accumulator_key]) + float(speed) * 0.5
        )
        if st.session_state[accumulator_key] >= 1.0:
            advance = int(st.session_state[accumulator_key])
            st.session_state[accumulator_key] -= advance
            st.session_state[index_key] = min(
                len(events) - 1,
                int(st.session_state[index_key]) + advance,
            )
            if st.session_state[index_key] >= len(events) - 1:
                st.session_state[playing_key] = False
    event_index = st.slider(
        "Sự kiện" if language == "vi" else "Event",
        min_value=0,
        max_value=len(events) - 1,
        key=index_key,
    )
    current = events[event_index]
    visible: set[str] = set()
    for event in events[: event_index + 1]:
        item_id = event.get("item_id")
        if not item_id:
            continue
        if event.get("event_type") == "item_loaded":
            visible.add(str(item_id))
        elif event.get("event_type") in {"item_unloaded", "item_delivered"}:
            visible.discard(str(item_id))
    all_item_ids = {
        str(item["item_id"])
        for container in scene["containers"]
        for item in container["items"]
    }
    event_type = str(current.get("event_type", ""))
    phase = (
        "loading"
        if "load" in event_type and "unload" not in event_type
        else "travel"
        if event_type in {"door_opened", "door_closed", "stop_completed"}
        else "unloading"
        if event_type in {"item_unloaded", "item_delivered"}
        else "simulation"
    )
    cards = st.columns(6)
    card_values = (
        ("Event", f"{event_index + 1}/{len(events)}"),
        ("Phase", phase),
        ("Type", current.get("event_type", "—")),
        ("Stop", current.get("delivery_stop_id") or "—"),
        ("Container", current.get("container_id") or "—"),
        ("Logical time", f"{float(current.get('simulation_time_seconds', 0.0)):.2f} s"),
    )
    for card, (label, value) in zip(cards, card_values):
        card.metric(label, value)
    replay_figure = create_figure(
        scene,
        language=language,
        item_opacity=DEFAULT_ITEM_OPACITY,
        selected_item_id=current.get("item_id"),
        dimmed_opacity=DEFAULT_DIMMED_OPACITY,
        hidden_item_ids=all_item_ids - visible,
        item_color_mode="delivery_stop",
    )
    st.plotly_chart(
        replay_figure,
        width="stretch",
        config={"displaylogo": False, "scrollZoom": True},
        key=f"sequential-chart-{run_dir.name}",
    )
    _render_logistics_route(
        run_dir,
        language,
        highlighted_stop_id=current.get("delivery_stop_id"),
        compact=True,
    )
    st.caption(
        (
            f"Còn trong container: {len(visible)} kiện · "
            f"Tổng thời gian logic: {float(metrics.get('logical_total_seconds', 0.0)):.2f} giây"
        )
        if language == "vi"
        else (
            f"Items in containers: {len(visible)} · "
            f"Total logical time: {float(metrics.get('logical_total_seconds', 0.0)):.2f} seconds"
        )
    )


def _parse_seed_text(value: str) -> tuple[int, ...]:
    tokens = value.replace(",", " ").split()
    if not tokens:
        raise ValueError("Enter at least one seed")
    try:
        seeds = tuple(int(token) for token in tokens)
    except ValueError as exc:
        raise ValueError("Seeds must be integers separated by commas or spaces") from exc
    if any(seed < 0 for seed in seeds):
        raise ValueError("Seeds must be zero or greater")
    if len(seeds) != len(set(seeds)):
        raise ValueError("Seeds must be unique; use repeats to measure timing variation")
    return seeds


def _render_benchmark_dashboard(
    summary: pd.DataFrame,
    results: pd.DataFrame,
    language: str,
    *,
    ranking: pd.DataFrame | None = None,
    pareto: pd.DataFrame | None = None,
    milp_gaps: pd.DataFrame | None = None,
    pairwise: pd.DataFrame | None = None,
) -> None:
    frame = summary.copy()
    if ranking is not None and not ranking.empty:
        derived_columns = ["algorithm", "lexicographic_rank", "is_lexicographic_winner"]
        ranking_view = ranking[[column for column in derived_columns if column in ranking]].drop_duplicates("algorithm")
        frame = frame.merge(ranking_view, on="algorithm", how="left")
    if pareto is not None and not pareto.empty and "is_pareto_optimal" in pareto:
        pareto_view = pareto[["algorithm", "is_pareto_optimal"]].drop_duplicates("algorithm")
        frame = frame.merge(pareto_view, on="algorithm", how="left")
    if milp_gaps is not None and not milp_gaps.empty:
        gap_columns = ["algorithm", "milp_reference_status", "container_gap_to_milp", "cost_gap_to_milp", "runtime_speedup_vs_milp"]
        gap_view = milp_gaps[[column for column in gap_columns if column in milp_gaps]].drop_duplicates("algorithm")
        frame = frame.merge(gap_view, on="algorithm", how="left")
    frame["algorithm_name"] = frame["algorithm"].map(lambda value: get_algorithm(str(value)).name_for(language))
    numeric_columns = (
        "success_rate", "used_containers_mean", "used_containers_std", "total_cost_mean",
        "total_cost_std", "algorithm_runtime_mean_seconds", "algorithm_runtime_std_seconds",
    )
    for column in numeric_columns:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    successful = frame[frame["success_rate"] > 0].copy()
    if successful.empty:
        st.error(t("benchmark_no_valid_solution", language))
    else:
        best_container_count = successful["used_containers_mean"].min()
        quality_ties = successful[successful["used_containers_mean"] == best_container_count]
        best_cost = quality_ties["total_cost_mean"].min()
        fastest = successful["algorithm_runtime_mean_seconds"].min()
        winner = successful.sort_values(
            ["success_rate", "used_containers_mean", "total_cost_mean", "algorithm_runtime_mean_seconds"],
            ascending=[False, True, True, True],
        ).iloc[0]
        cards = st.columns(5)
        values = (
            ("Thuật toán dẫn đầu" if language == "vi" else "Lexicographic winner", winner["algorithm_name"]),
            (t("benchmark_valid_algorithms", language), f"{len(successful)}/{len(frame)}"),
            (t("benchmark_best_containers", language), f"{best_container_count:g}"),
            (t("benchmark_best_cost", language), f"{best_cost:g}"),
            (t("benchmark_fastest", language), f"{fastest:.4f} s"),
        )
        for card, (label, value) in zip(cards, values):
            card.metric(label, value)

    quality_tab, runtime_tab, tradeoff_tab, data_tab = st.tabs([
        t("benchmark_quality_tab", language),
        t("benchmark_runtime_tab", language),
        t("benchmark_tradeoff_tab", language),
        t("benchmark_data_tab", language),
    ])
    common_layout = {"legend_title_text": "", "margin": {"l": 20, "r": 20, "t": 55, "b": 20}}
    with quality_tab:
        st.caption(t("benchmark_primary_note", language))
        quality_chart = px.bar(
            frame,
            x="algorithm_name",
            y="used_containers_mean",
            error_y="used_containers_std" if "used_containers_std" in frame.columns else None,
            color="algorithm_name",
            labels={
                "algorithm_name": t("algorithm", language),
                "used_containers_mean": t("containers_used", language),
            },
            title=t("benchmark_container_chart", language),
        )
        quality_chart.update_layout(**common_layout, showlegend=False)
        st.plotly_chart(quality_chart, width="stretch", config={"displaylogo": False})
        cost_chart = px.bar(
            frame,
            x="algorithm_name",
            y="total_cost_mean",
            error_y="total_cost_std" if "total_cost_std" in frame.columns else None,
            color="algorithm_name",
            labels={
                "algorithm_name": t("algorithm", language),
                "total_cost_mean": t("benchmark_cost", language),
            },
            title=t("benchmark_cost_chart", language),
        )
        cost_chart.update_layout(**common_layout, showlegend=False)
        st.plotly_chart(cost_chart, width="stretch", config={"displaylogo": False})
    with runtime_tab:
        runtime_chart = px.bar(
            frame,
            x="algorithm_name",
            y="algorithm_runtime_mean_seconds",
            error_y="algorithm_runtime_std_seconds" if "algorithm_runtime_std_seconds" in frame.columns else None,
            color="algorithm_name",
            log_y=True,
            labels={
                "algorithm_name": t("algorithm", language),
                "algorithm_runtime_mean_seconds": t("runtime", language),
            },
            title=t("benchmark_runtime_chart", language),
        )
        runtime_chart.update_layout(**common_layout, showlegend=False)
        st.plotly_chart(runtime_chart, width="stretch", config={"displaylogo": False})
        success_chart = px.bar(
            frame,
            x="algorithm_name",
            y="success_rate",
            color="algorithm_name",
            range_y=[0, 1.05],
            labels={"algorithm_name": t("algorithm", language), "success_rate": t("benchmark_success_rate", language)},
            title=t("benchmark_success_chart", language),
        )
        success_chart.update_layout(**common_layout, showlegend=False)
        st.plotly_chart(success_chart, width="stretch", config={"displaylogo": False})
    with tradeoff_tab:
        st.caption(t("benchmark_tradeoff_note", language))
        tradeoff_chart = px.scatter(
            frame,
            x="algorithm_runtime_mean_seconds",
            y="used_containers_mean",
            color="algorithm_name",
            size="success_rate",
            size_max=28,
            log_x=True,
            hover_data=[column for column in ["total_cost_mean", "objective_mean", "success_rate", "lexicographic_rank", "is_pareto_optimal", "container_gap_to_milp"] if column in frame],
            labels={
                "algorithm_runtime_mean_seconds": t("runtime", language),
                "used_containers_mean": t("containers_used", language),
                "algorithm_name": t("algorithm", language),
            },
            title=t("benchmark_tradeoff_chart", language),
        )
        tradeoff_chart.update_layout(**common_layout)
        st.plotly_chart(tradeoff_chart, width="stretch", config={"displaylogo": False})
    with data_tab:
        ranking_columns = [
            "lexicographic_rank", "is_lexicographic_winner", "is_pareto_optimal", "algorithm_name", "success_rate", "used_containers_mean", "used_containers_std",
            "total_cost_mean", "total_cost_std", "algorithm_runtime_mean_seconds",
            "algorithm_runtime_std_seconds", "container_gap_to_milp", "cost_gap_to_milp", "runtime_speedup_vs_milp", "objective_mean", "distinct_solution_count",
        ]
        ranking_columns = [value for value in ranking_columns if value in frame.columns]
        ranking = frame.sort_values(
            ["success_rate", "used_containers_mean", "total_cost_mean", "algorithm_runtime_mean_seconds"],
            ascending=[False, True, True, True],
        )
        st.dataframe(ranking[ranking_columns], hide_index=True, width="stretch")
        st.caption(t("benchmark_objective_note", language))
        if "is_pareto_optimal" in frame:
            pareto_algorithms = frame.loc[frame["is_pareto_optimal"].fillna(False), "algorithm_name"].tolist()
            if pareto_algorithms:
                st.caption(("Pareto: " if language == "vi" else "Pareto frontier: ") + ", ".join(pareto_algorithms))
        if pairwise is not None and not pairwise.empty:
            with st.expander("So sánh từng cặp" if language == "vi" else "Pairwise comparison"):
                st.dataframe(pairwise, hide_index=True, width="stretch")
        with st.expander(t("benchmark_raw_results", language)):
            st.dataframe(results, hide_index=True, width="stretch")


def _render_benchmark_comparison(
    level_id: str,
    root: Path,
    language: str,
    *,
    default_item_count: int,
    default_container_count: int,
    default_environment: str,
    config_overrides: dict[str, Any],
) -> None:
    level_algorithms = [value.algorithm_id for value in list_algorithms(level_id=level_id)]
    default_algorithms = [
        value for value in ("extreme_point_ffd", "extreme_point_best_fit", "maximal_space_best_fit")
        if value in level_algorithms
    ]
    if len(level_algorithms) < 2:
        st.info(
            "Level này hiện chỉ có một thuật toán nên chưa thể tạo benchmark so sánh."
            if language == "vi" else
            "This level currently has only one algorithm, so a comparison benchmark is not available yet."
        )
        return
    with st.expander(t("benchmark_create", language), expanded=True):
        st.caption(t("benchmark_create_note", language))
        algorithms = st.multiselect(
            t("benchmark_algorithms", language),
            level_algorithms,
            default=default_algorithms,
            format_func=lambda value: get_algorithm(value).name_for(language),
            key="benchmark_algorithms",
        )
        instance_columns = st.columns(4)
        benchmark_item_count = int(instance_columns[0].number_input(
            t("items", language), min_value=1, value=default_item_count, step=1, key="benchmark_item_count",
        ))
        benchmark_container_count = int(instance_columns[1].number_input(
            t("containers", language), min_value=1, value=default_container_count, step=1,
            key="benchmark_container_count",
        ))
        seed_text = instance_columns[2].text_input(
            t("benchmark_seed_list", language), value="7, 11, 19", key="benchmark_seed_list",
        )
        repeats = int(instance_columns[3].number_input(
            t("benchmark_repeats", language), min_value=1, max_value=20, value=1, step=1,
            key="benchmark_repeat_count",
        ))
        selection_columns = st.columns(2)
        item_selection_strategy = selection_columns[0].selectbox(
            t("benchmark_item_selection", language),
            ITEM_SELECTION_STRATEGIES,
            format_func=lambda value: t(f"item_selection_{value}", language),
            key="benchmark_item_selection",
        )
        item_selection_seed = int(selection_columns[1].number_input(
            t("benchmark_selection_seed", language),
            min_value=0,
            value=101,
            step=1,
            disabled=item_selection_strategy != "stable_random",
            key="benchmark_selection_seed",
        ))
        if "milp_big_m" in algorithms:
            st.warning(t("benchmark_milp_warning", language))
        run_benchmark_clicked = st.button(
            t("benchmark_run_button", language), type="primary", key="run_benchmark_comparison",
        )
        if run_benchmark_clicked:
            try:
                seeds = _parse_seed_text(seed_text)
                with st.spinner(t("benchmark_running", language)):
                    benchmark_result = execute_benchmark_comparison(
                        level_id=level_id,
                        algorithm_ids=algorithms,
                        item_count=benchmark_item_count,
                        container_count=benchmark_container_count,
                        seeds=seeds,
                        repeats=repeats,
                        environment=default_environment,
                        config_path=get_level(level_id).default_config,
                        root=root,
                        item_selection_strategy=item_selection_strategy,
                        item_selection_seed=item_selection_seed if item_selection_strategy == "stable_random" else None,
                        config_overrides=config_overrides,
                    )
                st.session_state["pending_benchmark_run_id"] = benchmark_result.benchmark_id
                if benchmark_result.successful:
                    st.success(t("benchmark_run_success", language))
                else:
                    st.warning(t("benchmark_run_partial", language))
            except Exception as exc:
                st.exception(exc)

    benchmarks = discover_benchmark_runs(level_id, root=root, limit=100)
    if not benchmarks:
        st.info(t("no_benchmarks", language))
        return
    benchmark_by_id = {value.run_id: value for value in benchmarks}
    run_ids = list(benchmark_by_id)
    pending_run_id = st.session_state.pop("pending_benchmark_run_id", None)
    if pending_run_id in benchmark_by_id:
        st.session_state["benchmark_run"] = pending_run_id
    selected_run_id = st.selectbox(
        t("benchmark_run", language),
        run_ids,
        format_func=lambda value: (
            f"{benchmark_by_id[value].created_at_utc} · {benchmark_by_id[value].status} · "
            f"{benchmark_by_id[value].successful_case_count}/{benchmark_by_id[value].case_count} cases · {value}"
        ),
        key="benchmark_run",
    )
    selected = benchmark_by_id[selected_run_id]
    benchmark_dir = selected.run_dir / "benchmark"
    def read_csv_or_empty(path: Path) -> pd.DataFrame:
        try:
            return pd.read_csv(path)
        except pd.errors.EmptyDataError:
            return pd.DataFrame()

    summary = read_csv_or_empty(benchmark_dir / "summary.csv")
    results = read_csv_or_empty(benchmark_dir / "results.csv")
    derived = {
        name: read_csv_or_empty(benchmark_dir / filename) if (benchmark_dir / filename).is_file() else pd.DataFrame()
        for name, filename in {
            "ranking": "ranking.csv", "pareto": "pareto_frontier.csv",
            "milp_gaps": "milp_reference_gaps.csv", "pairwise": "pairwise_comparison.csv",
        }.items()
    }

    st.caption(str(selected.run_dir))
    columns = st.columns(5)
    values = (
        (t("benchmark_status", language), selected.status),
        (t("benchmark_cases", language), selected.case_count),
        (t("benchmark_successful", language), selected.successful_case_count),
        (t("benchmark_seeds", language), ", ".join(str(value) for value in selected.random_seeds) or "—"),
        (t("benchmark_repeats", language), selected.repeats_per_seed or "—"),
    )
    for column, (label, value) in zip(columns, values):
        column.metric(label, value)

    st.markdown(f"**{t('benchmark_summary', language)}**")
    if "scenario_id" in summary.columns:
        scenario_columns = ["scenario_id"]
        if "scenario_description" in summary.columns:
            scenario_columns.append("scenario_description")
        scenario_frame = summary[scenario_columns].drop_duplicates().fillna("")
        scenario_labels = {
            f"{row.scenario_id} — {getattr(row, 'scenario_description', '')}": row.scenario_id
            for row in scenario_frame.itertuples(index=False)
        }
        selected_scenario_label = st.selectbox(
            "Kịch bản so sánh" if language == "vi" else "Comparable scenario",
            list(scenario_labels), key="benchmark_scenario",
        )
        selected_scenario = scenario_labels[selected_scenario_label]
        summary = summary[summary["scenario_id"] == selected_scenario].copy()
        if "scenario_id" in results.columns:
            results = results[results["scenario_id"] == selected_scenario].copy()
        for name, frame in derived.items():
            if "scenario_id" in frame.columns:
                derived[name] = frame[frame["scenario_id"] == selected_scenario].copy()
        if "input_fingerprint" in summary.columns and summary["input_fingerprint"].nunique() != 1:
            st.warning(
                "Kịch bản này có nhiều input fingerprint; không nên so sánh các dòng này như cùng một điều kiện."
                if language == "vi" else
                "This scenario has multiple input fingerprints; do not treat its rows as one comparable condition."
            )
    _render_benchmark_dashboard(summary, results, language, **derived)


def main() -> None:
    st.set_page_config(page_title="Mô phỏng xếp container 3D", page_icon="📦", layout="wide")
    root = find_project_root(__file__)
    language_label = st.sidebar.selectbox("Ngôn ngữ / Language", ["Tiếng Việt", "English"], key="language")
    language = "vi" if language_label == "Tiếng Việt" else "en"
    st.title(t("title", language))
    st.caption(t("caption", language))

    level_ids = [value.level_id for value in list_levels() if value.web_visible]
    level_id = st.sidebar.selectbox(t("level", language), level_ids, key="level_id")
    level = get_level(level_id)
    base_config_path = root / level.default_config
    base_config = load_config(base_config_path)
    algorithm_ids = [
        value.algorithm_id for value in list_algorithms(level_id=level_id)
        if value.web_visible
    ]
    configured_algorithm = str(base_config.get("project", {}).get("algorithm_id", algorithm_ids[0]))
    if configured_algorithm not in algorithm_ids:
        raise ValueError(f"Configured algorithm {configured_algorithm!r} is not compatible with {level_id}")
    if (
        st.session_state.get("_algorithm_level_id") != level_id
        or st.session_state.get("algorithm_id") not in algorithm_ids
    ):
        st.session_state["algorithm_id"] = configured_algorithm
        st.session_state["_algorithm_level_id"] = level_id
    algorithm_id = st.sidebar.selectbox(
        t("algorithm", language), algorithm_ids,
        format_func=lambda value: get_algorithm(value).name_for(language), key="algorithm_id",
    )
    algorithm = get_algorithm(algorithm_id)
    st.sidebar.caption(f"{algorithm_family(algorithm.family, language)}: {algorithm.description_for(language)}")
    if level_id == "level_08":
        st.sidebar.warning(
            "Level 8 đang ở mức thực nghiệm: LIFO dùng mô hình đường tháo thẳng tĩnh; chưa mô phỏng thiết bị, vùng chứa tạm hoặc chuỗi dỡ vật lý chính xác."
            if language == "vi" else
            "Level 8 is experimental: LIFO uses a static straight-path model; handling equipment, staging, and an exact physical unloading sequence are inactive."
        )
        st.sidebar.caption(
            "Demo web có preset 6/2, 20/5 và tùy chỉnh tối đa 100 kiện/10 container. Quy mô 300 tiếp tục chạy bằng CLI."
            if language == "vi" else
            "The web demo offers 6/2, 20/5, and custom profiles up to 100 items/10 containers. Keep 300-item research runs on the CLI."
        )

    level8_profile_id: str | None = None
    level8_profile: dict[str, Any] | None = None
    if level_id == "level_08":
        profiles = _level8_web_profiles(root)
        level8_profile_id = st.sidebar.selectbox(
            "Hồ sơ demo" if language == "vi" else "Demo profile",
            tuple(profiles),
            format_func=lambda value: profiles[value][
                "label_vi" if language == "vi" else "label_en"
            ],
            key="level_08_web_profile",
        )
        level8_profile = profiles[level8_profile_id]
        selected_config = Path(str(level8_profile["config_file"]))
    else:
        selected_config = level.config_for_algorithm(algorithm_id)
    config_path = root / selected_config
    config = load_config(config_path)

    limits = get_instance_limits(config_path, root=root)
    instance_defaults = config["instance"]
    instance_scope = (
        f"{level_id}:{level8_profile_id}" if level8_profile_id else level_id
    )
    if st.session_state.get("_instance_level_id") != instance_scope:
        st.session_state["item_count"] = int(instance_defaults["item_count"])
        st.session_state["container_count"] = int(instance_defaults["container_count"])
        st.session_state["_instance_level_id"] = instance_scope
        if level_id == "level_08":
            st.session_state["level_08_item_selection"] = "prefix"
            st.session_state["level_08_selection_seed"] = 42
    level8_fixed_profile = (
        level8_profile is not None and level8_profile.get("mode") == "fixed"
    )
    item_max = min(
        limits.available_items,
        int(level8_profile.get("item_count_max", limits.available_items))
        if level8_profile is not None
        else limits.available_items,
    )
    item_count = int(st.sidebar.number_input(
        t("items", language), min_value=1, max_value=item_max,
        step=1, key="item_count",
        disabled=level8_fixed_profile,
        help=(
            "Profile cố định khóa kích thước; chọn Demo nghiên cứu để thử tối đa 100 kiện."
            if language == "vi" and level8_fixed_profile else
            "Fixed profiles lock their size; choose Research demo for up to 100 items."
            if level8_fixed_profile else None
        ),
    ))
    container_max = (
        int(level8_profile.get("container_count_max", 10))
        if level8_profile is not None
        else max(limits.configured_containers, 1)
    )
    container_count = int(st.sidebar.number_input(
        t("containers", language), min_value=1,
        max_value=container_max if level_id == "level_08" else None,
        step=1, key="container_count",
        disabled=level8_fixed_profile,
        help=(
            "Profile cố định khóa số container; Demo nghiên cứu cho phép tối đa 10."
            if language == "vi" and level8_fixed_profile else
            "Fixed profiles lock the container count; Research demo allows up to 10."
            if level8_fixed_profile else
            f"Có {limits.configured_containers} container được cấu hình trực tiếp; số lớn hơn sẽ được mở rộng xác định cho Level 1."
            if language == "vi" else
            f"{limits.configured_containers} are explicitly configured; larger counts are deterministically extended Level 1 containers."
        ),
    ))
    item_selection_strategy = "prefix"
    item_selection_seed: int | None = None
    if level_id == "level_08":
        item_selection_strategy = st.sidebar.selectbox(
            "Cách chọn items" if language == "vi" else "Item selection",
            ("prefix", "stable_random"),
            key="level_08_item_selection",
        )
        item_selection_seed = int(
            st.sidebar.number_input(
                "Seed chọn tập" if language == "vi" else "Selection seed",
                min_value=0,
                step=1,
                key="level_08_selection_seed",
                disabled=item_selection_strategy != "stable_random",
            )
        )
    random_seed = int(st.sidebar.number_input(
        t("seed", language), min_value=0, value=int(config.get("project", {}).get("random_seed", 42)), step=1,
        key="random_seed",
    ))
    environment = st.sidebar.selectbox(t("environment", language), ["local", "colab", "kaggle"], key="environment")
    default_parameters = config.get("solver", {}) if algorithm_id == "milp_big_m" else config.get("algorithms", {}).get(algorithm_id, {})
    algorithm_parameters = _algorithm_parameters(algorithm_id, default_parameters, language)
    config_overrides = _level_config_overrides(level_id, config, language)
    route_input_blocked = False
    if level_id == "level_08" and algorithm_id in {
        "extreme_point_best_fit_delivery",
        "extreme_point_ffd_delivery",
    }:
        replay_enabled = st.sidebar.checkbox(
            "Bật replay bốc dỡ tuần tự" if language == "vi" else "Enable sequential replay",
            value=bool(config.get("sequential_simulation", {}).get("enabled", False)),
            key="level_08_sequential_replay",
            help=(
                "Replay là hard gate: trạng thái tháo dỡ vi phạm Level 1–8 sẽ làm nghiệm invalid."
                if language == "vi"
                else "Replay is a hard gate: any remaining state violating Levels 1–8 invalidates the run."
            ),
        )
        config_overrides = {
            **config_overrides,
            "sequential_simulation": {
                **dict(config.get("sequential_simulation", {})),
                "enabled": replay_enabled,
                "required_when_enabled": True,
            },
        }
        routing_config = dict(config.get("routing", {}))
        routing_enabled = st.sidebar.checkbox(
            "Bật bản đồ tuyến giao" if language == "vi" else "Enable route map",
            value=bool(routing_config.get("enabled", True)),
            key="level_08_routing_enabled",
        )
        routing_provider = st.sidebar.selectbox(
            "Nguồn tuyến đường" if language == "vi" else "Route provider",
            ("offline", "google_routes"),
            index=0 if routing_config.get("provider", "offline") == "offline" else 1,
            key="level_08_routing_provider",
            disabled=not routing_enabled,
        )
        uploaded_stops = st.sidebar.file_uploader(
            "CSV điểm giao (tùy chọn)"
            if language == "vi"
            else "Delivery stops CSV (optional)",
            type=("csv",),
            key="level_08_stops_upload",
            disabled=not routing_enabled,
        )
        stops_file = routing_config.get("stops_file")
        if uploaded_stops is not None:
            uploaded_path = _snapshot_uploaded_stops(uploaded_stops)
            uploaded_values = load_delivery_stops(uploaded_path)
            delivery_count = sum(
                value.stop_type == "delivery" for value in uploaded_values
            )
            if delivery_count > 10:
                route_input_blocked = True
                st.sidebar.error(
                    "Web demo chỉ cho phép tối đa 10 điểm giao."
                    if language == "vi"
                    else "The web demo allows at most 10 delivery stops."
                )
            else:
                stops_file = str(uploaded_path)
                st.sidebar.caption(
                    f"CSV SHA-256: {hashlib.sha256(uploaded_stops.getvalue()).hexdigest()[:12]}…"
                )
        if routing_provider == "google_routes" and not os.environ.get(
            "GOOGLE_ROUTES_API_KEY"
        ):
            st.sidebar.warning(
                "Thiếu GOOGLE_ROUTES_API_KEY; hệ thống sẽ fallback sang tuyến offline."
                if language == "vi"
                else "GOOGLE_ROUTES_API_KEY is missing; routing will fall back offline."
            )
        config_overrides = {
            **config_overrides,
            "routing": {
                **routing_config,
                "enabled": routing_enabled,
                "provider": routing_provider,
                "stops_file": stops_file,
                "fallback_to_offline": True,
            },
        }
    exact_reference_limit = _exact_reference_item_limit(algorithm_id, config)
    exact_reference_blocked = (
        exact_reference_limit is not None and item_count > exact_reference_limit
    )
    if exact_reference_blocked:
        st.sidebar.warning(t("exact_reference_limit", language).format(limit=exact_reference_limit))
    run_clicked = st.sidebar.button(
        t("run", language), type="primary", width="stretch", key="run_experiment",
        disabled=exact_reference_blocked or route_input_blocked,
    )

    if run_clicked:
        try:
            request = build_experiment_request(
                level_id=level_id, algorithm_id=algorithm_id,
                item_count=item_count, container_count=container_count,
                environment=environment, random_seed=random_seed,
                algorithm_parameters=algorithm_parameters,
                config_overrides=config_overrides,
                config_path=config_path, root=root,
                item_selection_strategy=item_selection_strategy,
                item_selection_seed=item_selection_seed,
            )
            with st.spinner(t("running", language)):
                result = execute_experiment(request)
            st.session_state["selected_run_dir"] = str(resolve_result_run_dir(result, root=root))
            if result.validation is None or not result.validation.valid:
                st.error(
                    f"Lượt chạy kết thúc với trạng thái {result.metadata.get('status')}; hãy xem tệp chẩn đoán bên dưới."
                    if language == "vi" else
                    f"Run finished with status {result.metadata.get('status')}; inspect its diagnostics below."
                )
            else:
                st.success(t("success", language))
        except Exception as exc:
            st.exception(exc)

    experiment_tab, benchmark_tab, contract_tab, history_tab = st.tabs([
        t("result_tab", language), t("benchmark_tab", language), t("contract_tab", language), t("history_tab", language),
    ])
    with experiment_tab:
        selected_run = st.session_state.get("selected_run_dir")
        if selected_run:
            _render_run(Path(selected_run), language)
        else:
            st.info(t("start_hint", language))
    with contract_tab:
        _render_level_contract(level_id, language)
    with benchmark_tab:
        _render_benchmark_comparison(
            level_id,
            root,
            language,
            default_item_count=item_count,
            default_container_count=container_count,
            default_environment=environment,
            config_overrides=config_overrides,
        )
    with history_tab:
        runs = discover_runs(level_id, root=root, limit=100)
        if not runs:
            st.info(t("no_runs", language))
        else:
            labels = {
                f"{value.created_at_utc} · {value.algorithm_id} · i{value.item_count}/c{value.container_count} · {value.validation_status}": value
                for value in runs
            }
            selected_label = st.selectbox(t("persisted_run", language), list(labels))
            if st.button(t("open_run", language)):
                st.session_state["selected_run_dir"] = str(labels[selected_label].run_dir)
                st.rerun()
            st.dataframe(pd.DataFrame([{
                ("Run" if language == "en" else "Mã run"): value.run_id,
                t("algorithm", language): value.algorithm_id,
                t("items_metric", language): value.item_count,
                ("Containers available" if language == "en" else "Container khả dụng"): value.container_count,
                t("status", language): value.status,
                t("validation", language): value.validation_status,
                ("Created" if language == "en" else "Thời điểm tạo"): value.created_at_utc,
            } for value in runs]), hide_index=True, width="stretch")


if __name__ == "__main__":
    main()
