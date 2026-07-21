"""Thin Streamlit research UI; all optimization remains in the core package."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from container_packing.algorithms.registry import get_algorithm, list_algorithms
from container_packing.application.service import (
    build_experiment_request,
    discover_runs,
    execute_experiment,
    get_instance_limits,
    resolve_result_run_dir,
)
from container_packing.data_loader import load_config
from container_packing.levels.registry import get_level, list_levels
from container_packing.runtime.project import find_project_root
from container_packing.visualization.plotly_3d import (
    DEFAULT_DIMMED_OPACITY,
    DEFAULT_ITEM_OPACITY,
    create_figure,
)
from container_packing.visualization.scene_schema import load_scene
from container_packing.web.i18n import algorithm_family, text as t

OPACITY_PRESETS = {"solid": DEFAULT_ITEM_OPACITY, "balanced": 0.75, "xray": 0.30}


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
        primary = st.columns(3)
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


def main() -> None:
    st.set_page_config(page_title="Mô phỏng xếp container 3D", page_icon="📦", layout="wide")
    root = find_project_root(__file__)
    language_label = st.sidebar.selectbox("Ngôn ngữ / Language", ["Tiếng Việt", "English"], key="language")
    language = "vi" if language_label == "Tiếng Việt" else "en"
    st.title(t("title", language))
    st.caption(t("caption", language))

    level_ids = [value.level_id for value in list_levels()]
    level_id = st.sidebar.selectbox(t("level", language), level_ids, key="level_id")
    level = get_level(level_id)
    algorithm_ids = [value.algorithm_id for value in list_algorithms(level_id=level_id)]
    algorithm_id = st.sidebar.selectbox(
        t("algorithm", language), algorithm_ids,
        format_func=lambda value: get_algorithm(value).name_for(language), key="algorithm_id",
    )
    algorithm = get_algorithm(algorithm_id)
    st.sidebar.caption(f"{algorithm_family(algorithm.family, language)}: {algorithm.description_for(language)}")

    config_path = root / level.default_config
    config = load_config(config_path)
    limits = get_instance_limits(config_path, root=root)
    instance_defaults = config["instance"]
    item_count = int(st.sidebar.number_input(
        t("items", language), min_value=1, max_value=limits.available_items,
        value=int(instance_defaults["item_count"]), step=1, key="item_count",
    ))
    container_count = int(st.sidebar.number_input(
        t("containers", language), min_value=1,
        value=int(instance_defaults["container_count"]), step=1, key="container_count",
        help=(
            f"Có {limits.configured_containers} container được cấu hình trực tiếp; số lớn hơn sẽ được mở rộng xác định cho Level 1."
            if language == "vi" else
            f"{limits.configured_containers} are explicitly configured; larger counts are deterministically extended Level 1 containers."
        ),
    ))
    random_seed = int(st.sidebar.number_input(
        t("seed", language), min_value=0, value=int(config.get("project", {}).get("random_seed", 42)), step=1,
        key="random_seed",
    ))
    environment = st.sidebar.selectbox(t("environment", language), ["local", "colab", "kaggle"], key="environment")
    default_parameters = config.get("solver", {}) if algorithm_id == "milp_big_m" else config.get("algorithms", {}).get(algorithm_id, {})
    algorithm_parameters = _algorithm_parameters(algorithm_id, default_parameters, language)
    run_clicked = st.sidebar.button(t("run", language), type="primary", width="stretch", key="run_experiment")

    if run_clicked:
        try:
            request = build_experiment_request(
                level_id=level_id, algorithm_id=algorithm_id,
                item_count=item_count, container_count=container_count,
                environment=environment, random_seed=random_seed,
                algorithm_parameters=algorithm_parameters,
                config_path=config_path, root=root,
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

    experiment_tab, contract_tab, history_tab = st.tabs([
        t("result_tab", language), t("contract_tab", language), t("history_tab", language),
    ])
    with experiment_tab:
        selected_run = st.session_state.get("selected_run_dir")
        if selected_run:
            _render_run(Path(selected_run), language)
        else:
            st.info(t("start_hint", language))
    with contract_tab:
        _render_level_contract(level_id, language)
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
