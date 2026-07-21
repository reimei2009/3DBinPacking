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
from container_packing.visualization.plotly_3d import create_figure
from container_packing.visualization.scene_schema import load_scene


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _algorithm_parameters(algorithm_id: str, defaults: dict[str, Any]) -> dict[str, Any]:
    parameters: dict[str, Any] = {}
    if algorithm_id == "milp_big_m":
        parameters["time_limit_seconds"] = st.sidebar.number_input(
            "MILP time limit (seconds)", min_value=1, value=int(defaults.get("time_limit_seconds", 600)), step=1,
        )
        parameters["mip_rel_gap"] = st.sidebar.number_input(
            "MILP relative gap", min_value=0.0, max_value=1.0,
            value=float(defaults.get("mip_rel_gap", 0.0)), step=0.001, format="%.4f",
        )
    else:
        parameters["subset_enumeration_limit"] = st.sidebar.number_input(
            "Container subset enumeration limit", min_value=1,
            value=int(defaults.get("subset_enumeration_limit", 12)), step=1,
        )
    if algorithm_id == "extreme_point_hill_climbing":
        parameters["max_iterations"] = st.sidebar.number_input(
            "Hill-climbing iterations", min_value=0, value=int(defaults.get("max_iterations", 10)), step=1,
        )
        parameters["max_neighbors"] = st.sidebar.number_input(
            "Neighbors per iteration", min_value=1, value=int(defaults.get("max_neighbors", 24)), step=1,
        )
    if algorithm_id == "extreme_point_simulated_annealing":
        parameters["max_iterations"] = st.sidebar.number_input(
            "Annealing iterations", min_value=0, value=int(defaults.get("max_iterations", 200)), step=10,
        )
        parameters["initial_temperature"] = st.sidebar.number_input(
            "Initial temperature", min_value=0.0001,
            value=float(defaults.get("initial_temperature", 0.25)), step=0.01, format="%.4f",
        )
        parameters["cooling_rate"] = st.sidebar.number_input(
            "Cooling rate", min_value=0.0001, max_value=0.9999,
            value=float(defaults.get("cooling_rate", 0.97)), step=0.001, format="%.4f",
        )
    return parameters


def _render_level_contract(level_id: str) -> None:
    level = get_level(level_id)
    contract = level.contract
    st.subheader(contract.title)
    st.write(contract.problem)
    st.markdown("**Objective**")
    for value in contract.objective:
        st.write(f"- {value}")
    st.markdown("**Mathematical variables**")
    st.dataframe(pd.DataFrame([{
        "Symbol": value.symbol,
        "Type": value.variable_type,
        "Indices": value.indices,
        "Meaning": value.meaning,
    } for value in contract.variables]), hide_index=True, width="stretch")
    st.markdown("**Active constraints**")
    st.dataframe(pd.DataFrame([{
        "ID": value.constraint_id, "Constraint": value.name, "Meaning": value.meaning,
    } for value in contract.active_constraints]), hide_index=True, width="stretch")
    left, right = st.columns(2)
    with left:
        st.markdown("**Assumptions**")
        for value in contract.assumptions:
            st.write(f"- {value}")
    with right:
        st.markdown("**Inactive in this level**")
        st.write(", ".join(contract.inactive_constraints))
    st.warning(" ".join(contract.limitations))
    st.info(contract.solution_claim)


def _render_run(run_dir: Path) -> None:
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        st.error(f"Missing manifest: {manifest_path}")
        return
    manifest = _read_json(manifest_path)
    metrics_path = run_dir / "metrics" / "metrics.json"
    metrics = _read_json(metrics_path) if metrics_path.is_file() else {}
    st.caption(str(run_dir))
    columns = st.columns(6)
    values = (
        ("Status", manifest.get("status", "unknown")),
        ("Validation", manifest.get("validation_status", "unknown")),
        ("Items", metrics.get("n_items", "—")),
        ("Containers used", metrics.get("container_count", "—")),
        ("Objective", metrics.get("objective_value", "—")),
        ("Runtime (s)", f"{float(metrics.get('algorithm_runtime_seconds', 0)):.3f}"),
    )
    for column, (label, value) in zip(columns, values):
        column.metric(label, value)
    scene_path = run_dir / "visualization" / "scene.json"
    if not scene_path.is_file():
        st.warning("This run has no valid visualization scene.")
        return
    scene = load_scene(scene_path)
    st.warning(scene["warning"])
    container_ids = [value["container_id"] for value in scene["containers"]]
    selected = st.selectbox("3D view", ["All used containers", *container_ids], key=f"view-{run_dir.name}")
    options = st.columns(2)
    labels = options[0].checkbox("Show item labels", value=False, key=f"labels-{run_dir.name}")
    boundaries = options[1].checkbox("Show container boundaries", value=True, key=f"bounds-{run_dir.name}")
    figure = create_figure(
        scene,
        container_id=None if selected == "All used containers" else selected,
        show_labels=labels,
        show_boundaries=boundaries,
    )
    st.plotly_chart(figure, width="stretch", config={"displaylogo": False, "scrollZoom": True})
    summary_path = run_dir / "solution" / "containers.csv"
    placements_path = run_dir / "solution" / "placements.csv"
    if summary_path.is_file():
        st.markdown("**Container utilization**")
        st.dataframe(pd.read_csv(summary_path), hide_index=True, width="stretch")
    if placements_path.is_file():
        with st.expander("Placements"):
            st.dataframe(pd.read_csv(placements_path), hide_index=True, width="stretch")


def main() -> None:
    st.set_page_config(page_title="3D Container Packing R&D", page_icon="📦", layout="wide")
    root = find_project_root(__file__)
    st.title("3D Container Packing — Research Console")
    st.caption("A thin UI over the same registry-driven pipeline used by CLI and notebooks.")

    level_ids = [value.level_id for value in list_levels()]
    level_id = st.sidebar.selectbox("Level", level_ids)
    level = get_level(level_id)
    algorithm_ids = [value.algorithm_id for value in list_algorithms(level_id=level_id)]
    algorithm_id = st.sidebar.selectbox("Algorithm", algorithm_ids)
    algorithm = get_algorithm(algorithm_id)
    st.sidebar.caption(f"{algorithm.family}: {algorithm.description}")

    config_path = root / level.default_config
    config = load_config(config_path)
    limits = get_instance_limits(config_path, root=root)
    instance_defaults = config["instance"]
    item_count = int(st.sidebar.number_input(
        "Number of items", min_value=1, max_value=limits.available_items,
        value=int(instance_defaults["item_count"]), step=1,
    ))
    container_count = int(st.sidebar.number_input(
        "Number of containers", min_value=1,
        value=int(instance_defaults["container_count"]), step=1,
        help=f"{limits.configured_containers} are explicitly configured; larger counts are deterministically extended Level 1 containers.",
    ))
    random_seed = int(st.sidebar.number_input(
        "Random seed", min_value=0, value=int(config.get("project", {}).get("random_seed", 42)), step=1,
    ))
    environment = st.sidebar.selectbox("Environment metadata", ["local", "colab", "kaggle"])
    default_parameters = config.get("solver", {}) if algorithm_id == "milp_big_m" else config.get("algorithms", {}).get(algorithm_id, {})
    algorithm_parameters = _algorithm_parameters(algorithm_id, default_parameters)
    run_clicked = st.sidebar.button("Run experiment", type="primary", width="stretch")

    if run_clicked:
        try:
            request = build_experiment_request(
                level_id=level_id, algorithm_id=algorithm_id,
                item_count=item_count, container_count=container_count,
                environment=environment, random_seed=random_seed,
                algorithm_parameters=algorithm_parameters,
                config_path=config_path, root=root,
            )
            with st.spinner("Preparing data, solving, and independently validating..."):
                result = execute_experiment(request)
            st.session_state["selected_run_dir"] = str(resolve_result_run_dir(result, root=root))
            if result.validation is None or not result.validation.valid:
                st.error(f"Run finished with status {result.metadata.get('status')}; inspect its diagnostics below.")
            else:
                st.success("Experiment completed and passed independent validation.")
        except Exception as exc:
            st.exception(exc)

    experiment_tab, contract_tab, history_tab = st.tabs(["Result & 3D", "Level contract", "Run history"])
    with experiment_tab:
        selected_run = st.session_state.get("selected_run_dir")
        if selected_run:
            _render_run(Path(selected_run))
        else:
            st.info("Choose the experiment inputs in the sidebar and click Run experiment.")
    with contract_tab:
        _render_level_contract(level_id)
    with history_tab:
        runs = discover_runs(level_id, root=root, limit=100)
        if not runs:
            st.info("No persisted runs exist for this level yet.")
        else:
            labels = {
                f"{value.created_at_utc} · {value.algorithm_id} · i{value.item_count}/c{value.container_count} · {value.validation_status}": value
                for value in runs
            }
            selected_label = st.selectbox("Persisted run", list(labels))
            if st.button("Open selected run"):
                st.session_state["selected_run_dir"] = str(labels[selected_label].run_dir)
                st.rerun()
            st.dataframe(pd.DataFrame([{
                "Run": value.run_id,
                "Algorithm": value.algorithm_id,
                "Items": value.item_count,
                "Containers available": value.container_count,
                "Status": value.status,
                "Validation": value.validation_status,
                "Created": value.created_at_utc,
            } for value in runs]), hide_index=True, width="stretch")


if __name__ == "__main__":
    main()
