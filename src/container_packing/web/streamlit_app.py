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
from container_packing.benchmarks import (
    load_benchmark_catalog,
    load_benchmark_corpus,
    run_benchmark_corpus,
)
from container_packing.benchmarks.distribution import (
    build_case_differences,
    build_distribution_summary,
)
from container_packing.application.service import (
    ActiveDataContext,
    build_experiment_request,
    discover_benchmark_runs,
    discover_runs,
    execute_benchmark_comparison,
    execute_experiment,
    get_benchmark_input_provenance,
    get_container_inventory_summary,
    get_inventory_request_preview,
    get_instance_limits,
    resolve_active_data_context,
    resolve_result_run_dir,
)
from container_packing.application.failure_explanation import explain_failure
from container_packing.data_loader import load_config, merge_config
from container_packing.levels.registry import get_level, list_levels
from container_packing.levels.level_08_routing import load_delivery_stops
from container_packing.instance_data import ITEM_SELECTION_STRATEGIES
from container_packing.provenance import sha256_file
from container_packing.runtime.project import find_project_root
from container_packing.visualization.plotly_3d import (
    DEFAULT_DIMMED_OPACITY,
    DEFAULT_ITEM_OPACITY,
    create_figure,
)
from container_packing.visualization.scene_schema import load_scene
from container_packing.web.i18n import algorithm_family, text as t
from container_packing.web.benchmark_charts import (
    build_quality_gap_figure,
    build_runtime_figure,
    summarize_against_baseline,
)

OPACITY_PRESETS = {"solid": DEFAULT_ITEM_OPACITY, "balanced": 0.75, "xray": 0.30}
_RUNTIME_UNSET = object()
_INVENTORY_BENCHMARK_ALGORITHMS = frozenset({
    "extreme_point_best_fit", "extreme_point_ffd", "maximal_space_best_fit",
})
_BENCHMARK_RUNTIME_PRESETS: dict[str, float | None | object] = {
    "30 giây": 30.0,
    "60 giây": 60.0,
    "90 giây": 90.0,
    "120 giây": 120.0,
    "Tùy chỉnh": _RUNTIME_UNSET,
    "Không giới hạn — local": None,
}


def _benchmark_inventory_supported(level_id: str, algorithms: list[str] | tuple[str, ...]) -> bool:
    return level_id in {"level_01", "level_02"} and bool(algorithms) and all(
        value in _INVENTORY_BENCHMARK_ALGORITHMS for value in algorithms
    )


def _benchmark_worst_case_runtime_seconds(
    algorithm_count: int, seed_count: int, repeats: int,
    time_limit_seconds: float | None,
) -> float | None:
    if min(algorithm_count, seed_count, repeats) <= 0:
        raise ValueError("Benchmark execution counts must be positive")
    if time_limit_seconds is None:
        return None
    if time_limit_seconds <= 0:
        raise ValueError("Benchmark runtime limit must be positive")
    return algorithm_count * seed_count * repeats * float(time_limit_seconds)


def _benchmark_requires_confirmation(
    *, item_count: int, worst_case_runtime_seconds: float | None,
) -> bool:
    return (
        item_count >= 500
        or worst_case_runtime_seconds is None
        or worst_case_runtime_seconds > 300
    )


def _benchmark_request_signature(payload: dict[str, Any]) -> str:
    """Return a stable UI request identity without persisting a runnable draft."""
    encoded = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@st.cache_data(show_spinner=False)
def _cached_inventory_request_preview(
    config_file: str,
    project_root: str,
    item_count: int,
    initial_count: int,
    maximum_count: int,
    selection_strategy: str,
    selection_seed: int | None,
):
    """Cache the read-only preview; its key contains every semantic input."""
    return get_inventory_request_preview(
        Path(config_file),
        item_count=item_count,
        initial_used_container_count=initial_count,
        max_used_container_count=maximum_count,
        item_selection_strategy=selection_strategy,
        item_selection_seed=selection_seed,
        root=Path(project_root),
    )


def _benchmark_inventory_config_overrides(
    base_overrides: dict[str, Any],
    *,
    enabled: bool,
    initial_count: int,
    maximum_count: int,
    automatically_increase: bool,
    time_limit_seconds: float | None,
    repair_enabled: bool,
    repair_budget_seconds: float,
) -> dict[str, Any]:
    """Tạo một overlay benchmark duy nhất và giữ nguyên guard nâng cao của profile."""
    resolved = dict(base_overrides)
    search = _inventory_search_overrides(
        dict(resolved.get("container_search", {})),
        enabled=enabled,
        initial_count=initial_count,
        maximum_count=maximum_count,
        automatically_increase=automatically_increase,
        time_limit_seconds=time_limit_seconds,
    )
    reserve = float(search.get("validation_reserve_seconds", 2.0))
    effective_repair = _effective_inventory_repair_budget(
        repair_budget_seconds,
        global_time_limit_seconds=time_limit_seconds,
        validation_reserve_seconds=reserve,
    )
    search = _inventory_repair_overrides(
        search, enabled=enabled and repair_enabled,
        time_limit_seconds=effective_repair,
    )
    resolved["container_search"] = search
    return resolved


def _level8_web_profiles(root: Path) -> dict[str, dict[str, Any]]:
    payload = load_config(root / "config/level_08/web_profiles.yaml")
    profiles = payload.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError("Level 8 web profile registry is empty")
    return {str(key): dict(value) for key, value in profiles.items()}


def _inventory_web_profiles(root: Path, level_id: str) -> dict[str, dict[str, Any]]:
    """Load versioned catalog choices for a level promoted to inventory search."""
    payload = load_config(root / "config" / level_id / "web_inventory_profiles.yaml")
    profiles = payload.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError(f"{level_id} inventory web profile registry is empty")
    visible: dict[str, dict[str, Any]] = {}
    for key, raw_value in profiles.items():
        value = dict(raw_value)
        gate_value = value.get("requires_web_gate")
        if gate_value:
            gate_path = (root / str(gate_value)).resolve()
            if not gate_path.is_file():
                continue
            try:
                gate = json.loads(gate_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not bool(gate.get("qualified", False)):
                continue
            expected_profile = value.get("dataset_profile_id")
            if expected_profile and gate.get("dataset_profile_id") != expected_profile:
                continue
            manifest_value = value.get("generation_manifest")
            if manifest_value:
                manifest_path = (root / str(manifest_value)).resolve()
                if not manifest_path.is_file() or gate.get(
                    "generation_manifest_checksum"
                ) != sha256_file(manifest_path):
                    continue
        visible[str(key)] = value
    if not visible:
        raise ValueError(f"{level_id} has no web-ready inventory profile")
    return visible


def _default_inventory_profile_id(profiles: dict[str, dict[str, Any]]) -> str:
    """Return the single declared UI default without relying on YAML order."""
    declared = [key for key, value in profiles.items() if bool(value.get("default", False))]
    if len(declared) > 1:
        raise ValueError("Inventory web profiles may declare at most one default")
    return declared[0] if declared else next(iter(profiles))


def _level1_inventory_web_profiles(root: Path) -> dict[str, dict[str, Any]]:
    """Compatibility wrapper for existing Level 1 UI consumers and tests."""
    return _inventory_web_profiles(root, "level_01")


def _inventory_search_overrides(
    base: dict[str, Any], *, enabled: bool, initial_count: int,
    maximum_count: int, automatically_increase: bool,
    time_limit_seconds: float | None | object = _RUNTIME_UNSET,
) -> dict[str, Any]:
    """Build the exact request overlay used by the inventory controls."""
    if initial_count <= 0 or maximum_count <= 0:
        raise ValueError("Inventory container counts must be positive")
    if initial_count > maximum_count:
        raise ValueError("Initial container count cannot exceed the maximum")
    resolved = {
        **base,
        "enabled": enabled,
        "initial_used_container_count": initial_count,
        "max_used_container_count": maximum_count,
        "automatically_increase_container_count": automatically_increase,
    }
    if time_limit_seconds is not _RUNTIME_UNSET:
        resolved["time_limit_seconds"] = time_limit_seconds
    return resolved


def _effective_inventory_repair_budget(
    requested_seconds: float,
    *,
    global_time_limit_seconds: float | None,
    validation_reserve_seconds: float,
) -> float:
    """Giới hạn repair để không chiếm phần thời gian dành cho validation."""
    requested = float(requested_seconds)
    reserve = float(validation_reserve_seconds)
    if requested <= 0:
        raise ValueError("Inventory repair budget must be positive")
    if reserve < 0:
        raise ValueError("Inventory validation reserve cannot be negative")
    if global_time_limit_seconds is None:
        return requested
    available = float(global_time_limit_seconds) - reserve
    if available <= 0:
        raise ValueError(
            "Inventory search deadline must exceed its validation reserve"
        )
    return min(requested, available)


def _inventory_repair_overrides(
    base: dict[str, Any], *, enabled: bool, time_limit_seconds: float,
) -> dict[str, Any]:
    """Overlay repair controls while preserving advanced profile settings."""
    if time_limit_seconds <= 0:
        raise ValueError("Inventory repair time limit must be positive")
    resolved = dict(base)
    consolidation = dict(resolved.get("consolidation", {}))
    elimination = dict(consolidation.get("container_elimination", {}))
    consolidation.update({
        "enabled": bool(enabled),
        "time_limit_seconds": float(time_limit_seconds),
    })
    elimination["enabled"] = bool(enabled)
    consolidation["container_elimination"] = elimination
    resolved["consolidation"] = consolidation
    return resolved


def _unbounded_inventory_search_allowed() -> bool:
    """Unlimited chỉ mặc định khả dụng trên máy local, không trên web deploy."""
    configured = os.environ.get("ALLOW_UNBOUNDED_INVENTORY_SEARCH")
    if configured is not None:
        return configured.strip().lower() in {"1", "true", "yes", "on"}
    return not bool(os.environ.get("RENDER") or os.environ.get("STREAMLIT_SHARING_MODE"))


def _level8_profile_metadata(
    profile_id: str, profile: dict[str, Any], config: dict[str, Any]
) -> dict[str, str]:
    """Return presentation metadata without coupling the UI to one registry schema."""
    paths = dict(config.get("paths", {}))
    identity = dict(config.get("data_identity", {}))
    data_kind = str(
        identity.get("profile_kind")
        or profile.get(
            "data_kind",
            "cross_level_comparable"
            if bool(profile.get("cross_level_comparable", False))
            else "semantic_fixture",
        )
    )
    dataset_id = str(
        identity.get("dataset_id")
        or profile.get("dataset_id")
        or config.get("dataset_id")
        or Path(str(paths.get("raw_items_csv", "undeclared"))).stem
    )
    catalog_id = str(
        identity.get("container_catalog_id")
        or profile.get("container_catalog_id")
        or config.get("container_catalog_id")
        or Path(str(paths.get("raw_containers_csv", "inline_containers"))).stem
    )
    return {
        "profile_id": profile_id,
        "data_kind": data_kind,
        "dataset_id": dataset_id,
        "container_catalog_id": catalog_id,
        "comparison_group_id": str(
            identity.get("comparison_group_id")
            or profile.get("comparison_group_id", "")
        ),
    }


def _configured_container_preview(
    root: Path, config: dict[str, Any], container_count: int
) -> pd.DataFrame:
    """Build a read-only preview from either a CSV catalog or inline containers."""
    raw_path = config.get("paths", {}).get("raw_containers_csv")
    if raw_path:
        path = Path(str(raw_path))
        path = path if path.is_absolute() else root / path
        frame = pd.read_csv(path, encoding="utf-8-sig")
    else:
        frame = pd.DataFrame(config.get("containers", []))
    if frame.empty:
        return frame
    if "availability" in frame:
        frame = frame[pd.to_numeric(frame["availability"], errors="coerce") == 1]
    frame = frame.head(container_count).copy()
    required_dimensions = {"length_mm", "width_mm", "height_mm"}
    if "volume_m3" not in frame and required_dimensions.issubset(frame.columns):
        frame["volume_m3"] = (
            pd.to_numeric(frame["length_mm"])
            * pd.to_numeric(frame["width_mm"])
            * pd.to_numeric(frame["height_mm"])
            / 1_000_000_000.0
        )
    columns = [
        "container_id", "length_mm", "width_mm", "height_mm",
        "volume_m3", "max_weight_kg", "cost",
    ]
    return frame[[value for value in columns if value in frame.columns]]


def _routing_provider_options(environ: dict[str, str] | None = None) -> tuple[str, ...]:
    """Google routing is selectable only when its server-side key is configured."""
    values = os.environ if environ is None else environ
    if str(values.get("GOOGLE_ROUTES_API_KEY", "")).strip():
        return ("offline", "google_routes")
    return ("offline",)


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
            "container_id": "Mã container", "container_type_id": "Loại container",
            "used": "Đã dùng", "item_count": "Số kiện",
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


def _container_type_usage_summary(frame: pd.DataFrame) -> pd.DataFrame:
    """Tổng hợp container đã dùng theo nhãn type của dữ liệu nguồn."""
    if frame.empty or "container_type_id" not in frame.columns:
        return pd.DataFrame()
    used = frame.loc[frame["used"].astype(bool)].copy()
    if used.empty:
        return pd.DataFrame()
    return (
        used.groupby("container_type_id", dropna=False, sort=True)
        .agg(
            container_count=("container_id", "count"),
            item_count=("item_count", "sum"),
            loaded_weight_kg=("loaded_weight_kg", "sum"),
            loaded_volume_m3=("loaded_volume_m3", "sum"),
            total_cost=("cost", "sum"),
        )
        .reset_index()
    )


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
    solver_path = run_dir / "solver" / "solver_summary.json"
    solver = _read_json(solver_path) if solver_path.is_file() else {}
    diagnostics_metadata = {**solver, **metrics}
    st.caption(str(run_dir))
    columns = st.columns(7)
    values = (
        (t("status", language), manifest.get("status", "unknown")),
        (t("validation", language), manifest.get("validation_status", "unknown")),
        (t("items_metric", language), metrics.get("n_items", "—")),
        (t("containers_used", language), metrics.get("container_count", "—")),
        (
            "Chi phí container" if language == "vi" else "Container cost",
            metrics.get("total_container_cost", "—"),
        ),
        (
            "Objective mã hóa" if language == "vi" else "Encoded objective",
            metrics.get("objective_value", "—"),
        ),
        (t("runtime", language), f"{float(metrics.get('algorithm_runtime_seconds', 0)):.3f}"),
    )
    for column, (label, value) in zip(columns, values):
        column.metric(label, value)
    failure = explain_failure(diagnostics_metadata, language=language)
    if failure is not None:
        st.error(f"{failure.title}: {failure.summary}")
        if failure.suggestions:
            st.info(" ".join(failure.suggestions))
        with st.expander(
            "Chẩn đoán kỹ thuật" if language == "vi" else "Technical diagnostics",
        ):
            st.code(failure.failure_class)
            for value in failure.evidence:
                st.write(f"- {value}")
    if diagnostics_metadata.get("container_consolidation_enabled"):
        overall_initial = diagnostics_metadata.get(
            "incumbent_initial_container_count", 0,
        )
        overall_final = diagnostics_metadata.get(
            "incumbent_final_container_count", overall_initial,
        )
        rebuild_candidates = diagnostics_metadata.get(
            "container_consolidation_candidates_evaluated", 0,
        )
        local_candidates = diagnostics_metadata.get(
            "container_elimination_candidates_evaluated", 0,
        )
        reason = diagnostics_metadata.get(
            "container_consolidation_termination_reason", "unknown",
        )
        lower_bound = diagnostics_metadata.get(
            "container_consolidation_aggregate_lower_bound", "—",
        )
        runtime = float(diagnostics_metadata.get(
            "container_consolidation_runtime_seconds", 0.0,
        ))
        improvements = int(diagnostics_metadata.get(
            "incumbent_improvement_count", 0,
        ))
        initial_cost = diagnostics_metadata.get("incumbent_initial_container_cost")
        final_cost = diagnostics_metadata.get("incumbent_final_container_cost")
        volume_pressure = diagnostics_metadata.get(
            "lower_bound_required_volume_utilization_ratio"
        )
        payload_pressure = diagnostics_metadata.get(
            "lower_bound_required_payload_utilization_ratio"
        )
        binding_resource = diagnostics_metadata.get(
            "lower_bound_binding_resource"
        )
        preserved = reason in {
            "consolidation_time_limit", "candidate_limit",
            "heuristic_consolidation_failed",
        } and int(overall_final or 0) <= int(overall_initial or 0)
        message = (
            f"Container: {overall_initial} → {overall_final}; "
            f"cải thiện được nhận: {improvements}; đã xét "
            f"{rebuild_candidates} rebuild và {local_candidates} local candidate; "
            f"runtime repair: {runtime:.3f}s; kết thúc: {reason}; "
            f"cận tổng hợp: {lower_bound}."
            if language == "vi" else
            f"Containers: {overall_initial} → {overall_final}; "
            f"accepted improvements: {improvements}; evaluated "
            f"{rebuild_candidates} rebuild and {local_candidates} local candidates; "
            f"repair runtime: {runtime:.3f}s; stop: {reason}; "
            f"aggregate lower bound: {lower_bound}."
        )
        if initial_cost is not None and final_cost is not None:
            message += (
                f" Chi phí: {float(initial_cost):g} → {float(final_cost):g}."
                if language == "vi" else
                f" Cost: {float(initial_cost):g} → {float(final_cost):g}."
            )
        if preserved:
            message += (
                " Incumbent hợp lệ ban đầu đã được giữ lại."
                if language == "vi" else
                " The validated incumbent was preserved."
            )
        if diagnostics_metadata.get("adaptive_cluster_elimination_enabled"):
            sizes = diagnostics_metadata.get(
                "adaptive_cluster_neighborhood_sizes_attempted", [],
            )
            failed_targets = len(diagnostics_metadata.get(
                "adaptive_cluster_failed_items_by_target", {},
            ))
            cluster_sizes = diagnostics_metadata.get(
                "adaptive_cluster_cluster_sizes_attempted", {},
            )
            failure_reasons = diagnostics_metadata.get(
                "adaptive_cluster_failure_reason_by_target", {},
            )
            message += (
                f" Neighborhood đã thử: {sizes}; target có failed-item evidence: "
                f"{failed_targets}; cluster-size đã thử: {cluster_sizes}; "
                f"lý do chưa đóng được target: {failure_reasons}."
                if language == "vi" else
                f" Neighborhoods tried: {sizes}; targets with failed-item evidence: "
                f"{failed_targets}; cluster sizes tried: {cluster_sizes}; "
                f"target close failures: {failure_reasons}."
            )
        if volume_pressure is not None and payload_pressure is not None:
            message += (
                f" Tại cận {lower_bound}, mức sử dụng lạc quan bắt buộc là "
                f"volume {100 * float(volume_pressure):.1f}% và payload "
                f"{100 * float(payload_pressure):.1f}%; tài nguyên chặt hơn: "
                f"{binding_resource}."
                if language == "vi" else
                f" At lower bound {lower_bound}, optimistic required utilization is "
                f"{100 * float(volume_pressure):.1f}% volume and "
                f"{100 * float(payload_pressure):.1f}% payload; tighter resource: "
                f"{binding_resource}."
            )
            if binding_resource == "payload":
                message += (
                    " Khoảng trống hình học có thể tồn tại vì container đã gần hết tải trọng."
                    if language == "vi" else
                    " Geometric space may remain because containers are near their payload limit."
                )
        st.markdown(
            "**Cải thiện nghiệm**" if language == "vi" else "**Solution improvement**"
        )
        if int(overall_final or 0) < int(overall_initial or 0):
            st.success(message)
        else:
            st.info(message)
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
        container_frame = pd.read_csv(summary_path)
        st.dataframe(_localized_frame(container_frame, language, "containers"), hide_index=True, width="stretch")
        by_type = _container_type_usage_summary(container_frame)
        if not by_type.empty:
            st.markdown("**Tổng hợp container đã dùng theo loại**" if language == "vi" else "**Used containers by type**")
            st.dataframe(by_type, hide_index=True, width="stretch")
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
) -> bool:
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
    if route.get("provider_used") == "offline":
        st.caption(
            "Tuyến offline theo delivery_priority; khoảng cách Haversine (đường chim bay), "
            "thời gian ước tính ở 35 km/h, không phản ánh mạng đường hoặc giao thông thực."
            if language == "vi"
            else "Offline route in delivery_priority order; Haversine straight-line distance "
            "and duration estimated at 35 km/h, not real roads or traffic."
        )
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
    if "wall_runtime_mean_seconds" not in frame.columns:
        frame["wall_runtime_mean_seconds"] = frame.get("algorithm_runtime_mean_seconds")
    numeric_columns = (
        "success_rate", "used_containers_mean", "used_containers_std", "total_cost_mean",
        "total_cost_std", "algorithm_runtime_mean_seconds", "algorithm_runtime_std_seconds",
        "wall_runtime_mean_seconds",
    )
    for column in numeric_columns:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    successful = frame[frame["success_rate"] > 0].copy()
    if successful.empty:
        st.error(t("benchmark_no_valid_solution", language))
        diagnostic_columns = [
            column for column in (
                "algorithm", "status", "search_termination_reason", "best_partial_placement_count",
                "aggregate_lower_bound", "candidate_subsets_evaluated", "error",
            ) if column in results.columns
        ]
        if diagnostic_columns:
            st.caption(
                "Vì sao các thuật toán chưa tạo được nghiệm" if language == "vi"
                else "Why the algorithms did not produce a solution"
            )
            diagnostics = results[diagnostic_columns].drop_duplicates().copy()
            if "algorithm" in diagnostics:
                diagnostics["algorithm"] = diagnostics["algorithm"].map(
                    lambda value: get_algorithm(str(value)).name_for(language)
                )
            if language == "vi":
                status_labels = {
                    "INFEASIBLE_HEURISTIC": "Heuristic chưa tìm được nghiệm",
                    "TIME_LIMIT": "Hết thời gian",
                    "PRECHECK_FAILED": "Yêu cầu không đủ sức chứa",
                    "INVALID_SOLUTION": "Nghiệm không qua kiểm định",
                }
                if "status" in diagnostics:
                    diagnostics["status"] = diagnostics["status"].map(
                        lambda value: status_labels.get(str(value), str(value))
                    )
                diagnostics = diagnostics.rename(columns={
                    "algorithm": "Thuật toán",
                    "status": "Kết quả",
                    "search_termination_reason": "Lý do dừng",
                    "best_partial_placement_count": "Số kiện đã xếp tốt nhất",
                    "aggregate_lower_bound": "Cận dưới container",
                    "candidate_subsets_evaluated": "Số phương án container đã thử",
                    "error": "Lỗi",
                })
            st.dataframe(
                diagnostics.fillna("Không có dữ liệu" if language == "vi" else "Not available"),
                hide_index=True, width="stretch",
            )
            st.info(
                (
                    "Đây là thất bại của quá trình tìm kiếm, không phải chứng minh bài toán vô nghiệm. "
                    "Hãy kiểm tra giới hạn container, thời gian chạy và số kiện đã xếp tốt nhất."
                ) if language == "vi" else (
                    "This is a search failure, not a proof of infeasibility. Review the container "
                    "limit, runtime, and best partial placement count."
                )
            )
            with st.expander("Chi tiết kỹ thuật" if language == "vi" else "Technical details"):
                st.dataframe(
                    results[diagnostic_columns].drop_duplicates(),
                    hide_index=True, width="stretch",
                )
    else:
        best_container_count = successful["used_containers_mean"].min()
        quality_ties = successful[successful["used_containers_mean"] == best_container_count]
        fastest = successful["wall_runtime_mean_seconds"].min()
        quality_count = len(
            successful[["used_containers_mean", "total_cost_mean"]].drop_duplicates()
        )
        quality_label = (
            "Chất lượng hòa" if quality_count == 1 else "Có khác biệt"
        ) if language == "vi" else (
            "Quality tie" if quality_count == 1 else "Quality differs"
        )
        cards = st.columns(4)
        values = (
            ("Kết luận chất lượng" if language == "vi" else "Quality conclusion", quality_label),
            (
                t("benchmark_valid_algorithms", language),
                f"{len(successful)} trên {len(frame)}"
                if language == "vi" else f"{len(successful)} of {len(frame)}",
            ),
            (t("benchmark_best_containers", language), f"{best_container_count:g}"),
            (
                "Thời gian toàn quy trình nhanh nhất" if language == "vi" else "Fastest end-to-end time",
                f"{fastest:.4f} s",
            ),
        )
        for card, (label, value) in zip(cards, values):
            card.metric(label, value)

    quality_tab, runtime_tab, data_tab = st.tabs([
        t("benchmark_quality_tab", language),
        "Thời gian và độ tin cậy" if language == "vi" else "Runtime and reliability",
        "Từng bài kiểm tra" if language == "vi" else "Individual cases",
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
            y="wall_runtime_mean_seconds",
            color="algorithm_name",
            log_y=True,
            labels={
                "algorithm_name": t("algorithm", language),
                "wall_runtime_mean_seconds": (
                    "Thời gian toàn quy trình (giây)" if language == "vi"
                    else "End-to-end runtime (seconds)"
                ),
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
    with data_tab:
        ranking_columns = [
            "lexicographic_rank", "is_lexicographic_winner", "is_pareto_optimal", "algorithm_name", "success_rate", "used_containers_mean", "used_containers_std",
            "total_cost_mean", "total_cost_std", "wall_runtime_mean_seconds",
            "container_gap_to_milp", "cost_gap_to_milp", "runtime_speedup_vs_milp", "distinct_solution_count",
        ]
        ranking_columns = [value for value in ranking_columns if value in frame.columns]
        ranking = frame.sort_values(
            ["success_rate", "used_containers_mean", "total_cost_mean", "wall_runtime_mean_seconds"],
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


def _render_distribution_dashboard(
    distribution: pd.DataFrame,
    outcomes: pd.DataFrame,
    language: str,
    *,
    baseline_algorithm: str = "extreme_point_best_fit",
    results: pd.DataFrame | None = None,
    determinism: pd.DataFrame | None = None,
    run_label: str | None = None,
) -> None:
    """Render normalized multi-case evidence without averaging raw objectives."""
    if distribution.empty:
        return
    frame = distribution.copy()
    if results is not None and not results.empty:
        try:
            frame = build_distribution_summary(
                results, baseline_algorithm=baseline_algorithm,
            )
        except ValueError:
            # Artifact legacy vẫn dùng được bằng bảng distribution đã persist.
            frame = distribution.copy()
    frame["algorithm_name"] = frame["algorithm"].map(
        lambda value: get_algorithm(str(value)).name_for(language)
    )
    frame["case_count"] = pd.NA
    if results is not None and not results.empty:
        identity_column = "case_id" if "case_id" in results else "scenario_id"
        if identity_column in results and {"algorithm", "item_count"}.issubset(results.columns):
            case_counts = (
                results.groupby(["algorithm", "item_count"], dropna=False)[identity_column]
                .nunique().rename("case_count").reset_index()
            )
            frame = frame.drop(columns=["case_count"]).merge(
                case_counts, on=["algorithm", "item_count"], how="left", validate="one_to_one",
            )
    for column in ("runtime_min_seconds", "runtime_max_seconds"):
        if column not in frame:
            frame[column] = frame.get("runtime_p50_seconds")
    if "runtime_p95_seconds" not in frame:
        frame["runtime_p95_seconds"] = pd.NA
    baseline_rows: list[dict[str, object]] = []
    if not outcomes.empty:
        for row in outcomes.itertuples(index=False):
            left = str(row.algorithm_a)
            right = str(row.algorithm_b)
            outcome = str(row.outcome_for_a)
            if left == baseline_algorithm and right != baseline_algorithm:
                mapped = {"WIN": "LOSS", "LOSS": "WIN"}.get(outcome, outcome)
                baseline_rows.append({"algorithm": right, "outcome": mapped})
            elif right == baseline_algorithm and left != baseline_algorithm:
                baseline_rows.append({"algorithm": left, "outcome": outcome})
    baseline_frame = pd.DataFrame(baseline_rows)
    counts = pd.DataFrame()
    if not baseline_frame.empty:
        counts = baseline_frame.groupby(["algorithm", "outcome"]).size().reset_index(name="count")
        counts["algorithm_name"] = counts["algorithm"].map(lambda value: get_algorithm(str(value)).name_for(language))

    execution_count = int(frame["execution_count"].sum())
    valid_execution_count = int(round((frame["execution_count"] * frame["valid_rate"]).sum()))
    case_count = 0
    if results is not None and not results.empty:
        identity = results.get("case_id", results.get("scenario_id", pd.Series(dtype=str)))
        case_count = int(identity.replace("", pd.NA).dropna().nunique())
    conclusion, conclusion_details = summarize_against_baseline(
        outcomes,
        baseline_algorithm=baseline_algorithm,
        algorithm_name=lambda value: get_algorithm(value).name_for(language),
        language=language,
    )

    overview_tab, quality_tab, performance_tab = st.tabs([
        "Kết luận" if language == "vi" else "Conclusion",
        "Chất lượng" if language == "vi" else "Quality",
        "Thời gian và tài nguyên" if language == "vi" else "Runtime and resources",
    ])
    with overview_tab:
        if run_label:
            st.info(run_label)
        cards = st.columns(4)
        cards[0].metric("Bài kiểm tra" if language == "vi" else "Test cases", case_count or "—")
        cards[1].metric("Lượt chạy" if language == "vi" else "Executions", execution_count)
        cards[2].metric(
            "Lượt chạy hợp lệ" if language == "vi" else "Valid executions",
            f"{valid_execution_count}/{execution_count}",
        )
        repeat_checked = bool(
            determinism is not None
            and not determinism.empty
            and pd.to_numeric(determinism.get("repeat_count"), errors="coerce").max() >= 2
        )
        if repeat_checked:
            deterministic_count = int(determinism["deterministic"].fillna(False).sum())
            deterministic_label = f"{deterministic_count}/{len(determinism)}"
        else:
            deterministic_label = "Chưa kiểm tra" if language == "vi" else "Not checked"
        cards[3].metric("Tính xác định" if language == "vi" else "Determinism", deterministic_label)
        if valid_execution_count == execution_count:
            st.success(conclusion)
        else:
            st.warning(conclusion)
        for detail in conclusion_details:
            st.markdown(f"- {detail}")
        if conclusion_details:
            st.caption(
                "Khác biệt thời gian chạy không tham gia objective chính thức."
                if language == "vi" else
                "Runtime differences do not participate in the official objective."
            )
        st.caption(
            "Best Fit là mốc đối chiếu, không phải nghiệm tối ưu đã được chứng minh. "
            "Không lấy trung bình số container hoặc objective giữa các quy mô khác nhau."
            if language == "vi" else
            "Best Fit is a baseline, not a proven optimum. Raw container counts and objectives are not averaged across scales."
        )

    with quality_tab:
        if not counts.empty:
            st.plotly_chart(
            px.bar(
                counts, x="algorithm_name", y="count", color="outcome", barmode="stack",
                category_orders={"outcome": ["WIN", "TIE", "LOSS", "NO_VALID_SOLUTION"]},
                labels={
                    "algorithm_name": "Thuật toán" if language == "vi" else "Algorithm",
                    "count": "Số bài kiểm tra" if language == "vi" else "Cases",
                    "outcome": "So với Best Fit" if language == "vi" else "Versus Best Fit",
                },
                title="Thắng / hòa / thua so với Best Fit" if language == "vi" else "Win / tie / loss versus Best Fit",
            ),
            width="stretch", config={"displaylogo": False},
        )
            st.caption(
                "Mỗi bài được so với Best Fit trên đúng cùng dữ liệu. Thắng nghĩa là dùng ít "
                "container hơn, hoặc chi phí thấp hơn khi số container bằng nhau."
                if language == "vi" else
                "Each case uses the exact same input as Best Fit. A win means fewer containers, or lower cost when counts tie."
            )
        differences = pd.DataFrame()
        if results is not None and not results.empty:
            try:
                differences = build_case_differences(results)
            except ValueError:
                differences = pd.DataFrame()
        if not differences.empty:
            display = differences.copy()
            def _case_display_label(row: pd.Series) -> str:
                item_count = int(row["item_count"])
                strategy = str(row.get("item_selection_strategy", "") or "")
                seed = row.get("item_selection_seed")
                if strategy == "prefix":
                    return f"{item_count} kiện · prefix"
                if strategy == "stable_random" and pd.notna(seed):
                    return f"{item_count} kiện · random seed {int(seed)}"
                return f"{item_count} kiện · {strategy or 'cách chọn khác'}"

            display["Bài kiểm tra"] = display.apply(_case_display_label, axis=1)
            display["Thuật toán"] = display["algorithm"].map(
                lambda value: get_algorithm(str(value)).name_for(language)
            )
            display = display.rename(columns={
                "used_container_count": "Số container",
                "total_container_cost": "Chi phí",
            })
            st.markdown("**Các bài tạo khác biệt**" if language == "vi" else "**Cases that differ**")
            st.dataframe(
                display[["Bài kiểm tra", "Thuật toán", "Số container", "Chi phí"]],
                hide_index=True, width="stretch",
            )
            st.caption(
                "Bảng chỉ hiện các bài mà ít nhất hai thuật toán cho official objective khác nhau."
                if language == "vi" else
                "Only cases where at least two algorithms produce different official objectives are shown."
            )
        if "container_gap_lower_bound_median" in frame and frame["container_gap_lower_bound_median"].notna().any():
            st.plotly_chart(
                build_quality_gap_figure(frame, language=language),
                width="stretch", config={"displaylogo": False},
            )
            st.caption(
                "Điểm trung tính nghĩa là các thuật toán có cùng median và min–max ở quy mô đó; "
                "điều này không khẳng định mọi bài đều hòa. Điểm riêng thể hiện khác biệt giữa các "
                "thuật toán. Giá trị thấp hơn thường tốt hơn, nhưng cận dưới chưa chứng minh khả thi hình học."
                if language == "vi" else
                "A neutral point means algorithms share the same median and min–max at that scale; it does not mean every case ties. Separate points show algorithm differences. Lower is usually better, but the bound does not prove geometric feasibility."
            )
        else:
            st.info(
                "Artifact này chưa có cận tối thiểu sơ bộ; biểu đồ khoảng cách được ẩn."
                if language == "vi" else "This artifact has no aggregate lower-bound telemetry; the gap chart is hidden."
            )
    with performance_tab:
        runtime = frame.copy()
        runtime_chart = build_runtime_figure(runtime, language=language)
        p95 = runtime[runtime.get("runtime_p95_seconds", pd.Series(index=runtime.index)).notna()]
        for algorithm_name, values in p95.groupby("algorithm_name", sort=True):
            runtime_chart.add_scatter(
                x=values["item_count"], y=values["runtime_p95_seconds"],
                mode="lines+markers", line={"dash": "dot"},
                name=f"{algorithm_name} — 95% lượt chạy hoàn thành trong",
            )
        st.plotly_chart(runtime_chart, width="stretch", config={"displaylogo": False})
        if p95.empty:
            st.caption(
                "Chưa hiển thị p95 vì mỗi nhóm có dưới 10 lượt chạy; thanh sai số biểu diễn min–max."
                if language == "vi" else "p95 is hidden because each group has fewer than 10 executions; error bars show min–max."
            )
        st.caption(
            "Đây là thời gian toàn pipeline mà người dùng phải chờ. Điểm là trung vị; thanh sai số "
            "là min–max. Rê chuột theo một quy mô để xem đồng thời mọi thuật toán; bấm tên trong "
            "chú giải để ẩn/hiện, hoặc bấm đúp để cô lập một thuật toán. Runtime riêng của thuật toán "
            "nằm trong Chi tiết kỹ thuật."
            if language == "vi" else
            "This is user-visible end-to-end pipeline time. Points are medians and error bars are min–max. Hover a scale to compare all algorithms; use the legend to hide or isolate traces. Algorithm-only runtime stays in technical details."
        )

        reliability = frame.melt(
            id_vars=["item_count", "algorithm_name"],
            value_vars=[column for column in ("valid_rate", "timeout_rate", "invalid_rate") if column in frame],
            var_name="result_kind", value_name="rate",
        )
        if not reliability.empty:
            reliability["result_kind"] = reliability["result_kind"].map({
                "valid_rate": "Hợp lệ", "timeout_rate": "Hết thời gian", "invalid_rate": "Không hợp lệ",
            }).fillna(reliability["result_kind"])
            st.plotly_chart(
                px.bar(
                    reliability, x="item_count", y="rate", color="result_kind",
                    facet_col="algorithm_name", barmode="stack",
                    labels={"item_count": "Số kiện", "rate": "Tỷ lệ", "result_kind": "Kết quả"},
                    title="Tỷ lệ hợp lệ, hết thời gian và không hợp lệ",
                ), width="stretch", config={"displaylogo": False},
            )
            st.caption(
                "Biểu đồ cho biết tỷ lệ lượt chạy hợp lệ, hết thời gian hoặc bị validator từ chối ở từng quy mô."
                if language == "vi" else
                "This chart shows valid, timed-out and validator-rejected execution rates at each scale."
            )
        memory_column = None
        memory_title = None
        if "peak_memory_p95_bytes" in frame and frame["peak_memory_p95_bytes"].notna().any():
            memory_column = "peak_memory_p95_bytes"
            memory_title = "Bộ nhớ p95 theo quy mô"
        elif "peak_memory_max_bytes" in frame:
            memory_column = "peak_memory_max_bytes"
            memory_title = "Bộ nhớ lớn nhất đã quan sát theo quy mô"
        if memory_column:
            memory = frame.copy()
            memory["peak_memory_display_mb"] = pd.to_numeric(
                memory[memory_column], errors="coerce",
            ) / (1024 * 1024)
            st.plotly_chart(
                px.line(
                    memory, x="item_count", y="peak_memory_display_mb", color="algorithm_name",
                    markers=True,
                    labels={"item_count": "Số kiện", "peak_memory_display_mb": "Bộ nhớ (MB)", "algorithm_name": "Thuật toán"},
                    title=memory_title,
                ), width="stretch", config={"displaylogo": False},
            )
            st.caption(
                "Bộ nhớ cao hơn nghĩa là cần nhiều RAM hơn. Khi chưa đủ 10 mẫu, biểu đồ dùng mức lớn nhất đã quan sát thay cho p95."
                if language == "vi" else
                "Higher values require more RAM. With fewer than 10 samples, the chart uses the observed maximum instead of p95."
            )

    if results is not None and not results.empty:
        with st.expander("Từng bài kiểm tra" if language == "vi" else "Individual test cases"):
            display = results.copy()
            if "algorithm" in display:
                display["algorithm"] = display["algorithm"].map(
                    lambda value: get_algorithm(str(value)).name_for(language)
                )
            columns = [column for column in (
                "case_id", "item_count", "item_selection_strategy", "algorithm",
                "status", "used_container_count", "total_container_cost",
                "aggregate_lower_bound", "wall_runtime_seconds",
            ) if column in display]
            st.dataframe(display[columns], hide_index=True, width="stretch")
        with st.expander("Chi tiết kỹ thuật" if language == "vi" else "Technical details"):
            technical_columns = [column for column in (
                "case_id", "algorithm", "input_fingerprint", "algorithm_runtime_seconds",
                "wall_runtime_seconds", "peak_rss_bytes", "selected_item_ids_checksum",
            ) if column in results]
            st.dataframe(results[technical_columns], hide_index=True, width="stretch")


def _render_level2_benchmark_catalog(
    root: Path, language: str, active_data: ActiveDataContext,
) -> None:
    catalog = load_benchmark_catalog(
        root / "config/level_02/benchmarks/registry.yaml", project_root=root,
    )
    canonical = catalog.get("level_02_generated_canonical_v1")
    corpus = load_benchmark_corpus(canonical.protocol_file, project_root=root)
    scales = sorted({case.item_count for case in corpus.cases})
    execution_count = sum(len(case.algorithms) for case in corpus.cases) * len(corpus.seeds) * corpus.repeats
    saved_runs = discover_benchmark_runs(
        "level_02", root=root, limit=200,
        dataset_profile_id=active_data.profile_id,
        expected_raw_items_checksum=active_data.raw_items_checksum,
        expected_container_catalog_checksum=active_data.container_catalog_checksum,
    )
    canonical_run = next((
        run for run in saved_runs
        if run.suite_id == corpus.corpus_id
        and run.case_count == 24
        and run.execution_count == 144
        and run.successful_execution_count == 144
        and run.status == "SUCCESS"
    ), None)
    quick_entry = catalog.get("level_02_generated_quick_v3")
    quick_corpus = load_benchmark_corpus(quick_entry.protocol_file, project_root=root)
    quick_run = next((
        run for run in saved_runs
        if run.suite_id == quick_corpus.corpus_id
        and run.case_count == 6
        and run.execution_count == 18
    ), None)
    with st.expander("Benchmark chuẩn" if language == "vi" else "Standard benchmark", expanded=True):
        st.write(
            "Bộ đề cố định dùng để đánh giá thuật toán qua nhiều trường hợp, không phải một lần chạy tùy ý."
            if language == "vi" else
            "A fixed protocol used to evaluate algorithms across many cases, not one ad-hoc run."
        )
        cards = st.columns(4)
        cards[0].metric("Nguồn dữ liệu", "1.000 kiện / 500 container")
        cards[1].metric("Quy mô", ", ".join(str(value) for value in scales))
        cards[2].metric("Số bài kiểm tra", len(corpus.cases))
        cards[3].metric("Tổng lượt chạy", execution_count)
        status_cards = st.columns(2)
        status_cards[0].metric(
            "Benchmark chuẩn 144 lượt",
            "Đã hoàn thành" if canonical_run else "Chưa chạy",
        )
        status_cards[1].metric(
            "Kiểm tra nhanh 18 lượt",
            (
                f"{quick_run.successful_execution_count}/18 hợp lệ"
                if quick_run else "Chưa chạy"
            ),
        )
        st.markdown(
            "**Mốc đối chiếu:** Extreme Point Best Fit · **Repair:** tắt · "
            "**Lặp lại:** 2 lần để kiểm tra tính xác định."
        )
        st.caption(
            "Giới hạn thời gian: 20/50 kiện — 30 giây; 100 — 60 giây; "
            "200/300 — 90 giây; 500 — 120 giây cho mỗi lượt chạy."
        )
        quick = quick_entry
        source_matches = (
            active_data.profile_id == "level_02_inventory_items_1000_fleet_500_t10_v1"
        )
        if not source_matches:
            st.warning(
                "Nguồn đang chọn không phải nguồn chuẩn 1.000/500. Bạn vẫn có thể xem kết quả đã lưu, "
                "nhưng không thể chạy bản nhanh từ nguồn khác."
            )
        if st.button(
            "Chạy kiểm tra nhanh (20, 50, 100 kiện)" if language == "vi" else "Run quick benchmark",
            key="level2_run_canonical_quick", disabled=not source_matches,
        ):
            with st.spinner("Đang chạy 18 lượt kiểm tra ngắn…"):
                result = run_benchmark_corpus(quick.protocol_file, project_root=root)
            st.session_state["pending_benchmark_run_id"] = result.run_id
            st.session_state["benchmark_show_saved_results"] = True
            if result.successful:
                st.success("Kiểm tra nhanh hoàn tất; tất cả lượt chạy đạt kỳ vọng.")
            else:
                st.warning("Kiểm tra nhanh đã hoàn tất nhưng có lượt thất bại hoặc không hợp lệ.")
        with st.expander("Chi tiết kỹ thuật", expanded=False):
            st.write(f"Mã protocol: {corpus.corpus_id}")
            st.write(f"Tệp cấu hình: {canonical.protocol_file.relative_to(root)}")
            st.code(
                ".\\.venv\\Scripts\\python.exe .\\scripts\\run_benchmark_corpus.py `\n"
                "  --corpus config\\level_02\\benchmarks\\generated_1k_500_distribution_corpus.yaml",
                language="powershell",
            )

    candidate_entries = (
        catalog.get("level_02_generated_random_v2_candidate"),
        catalog.get("level_02_generated_stress_v2_candidate"),
        catalog.get("level_02_generated_prefix_v2_candidate"),
    )
    candidate_corpora = [
        load_benchmark_corpus(entry.protocol_file, project_root=root)
        for entry in candidate_entries
    ]
    with st.expander(
        "Benchmark V2 đang đánh giá" if language == "vi" else "Benchmark V2 candidate",
        expanded=False,
    ):
        st.write(
            "V2 tăng độ phủ nhưng chưa thay benchmark chuẩn V1. Ba nhóm được chạy và "
            "đánh giá riêng để stress case không làm lệch kết luận từ các mẫu random."
            if language == "vi" else
            "V2 expands coverage but does not replace V1 yet. Its three strata are evaluated separately."
        )
        labels = (
            ("Phân phối random", "Đánh giá tổng quát", 60, 540),
            ("Tình huống khó", "Đánh giá sức chịu đựng", 18, 162),
            ("Hồi quy theo nguồn", "Phát hiện thay đổi hành vi", 6, 54),
        )
        for entry, candidate, (label, purpose, expected_cases, expected_executions) in zip(
            candidate_entries, candidate_corpora, labels, strict=True,
        ):
            completed = next((
                run for run in saved_runs
                if run.suite_id == candidate.corpus_id
                and run.case_count == expected_cases
                and run.execution_count == expected_executions
                and run.successful_execution_count == expected_executions
                and run.status == "SUCCESS"
            ), None)
            columns = st.columns((2, 2, 1, 1))
            columns[0].markdown(f"**{label}**")
            columns[1].write(purpose)
            columns[2].write(f"{expected_cases} bài")
            columns[3].write("Đạt" if completed else "Chưa chạy")
        st.caption(
            "Tổng protocol: 84 bài, 756 lượt. Ba lần lặp chỉ đo nhiễu runtime và "
            "tính xác định; không được tính thành ba bài độc lập."
        )
        with st.expander("Chi tiết kỹ thuật", expanded=False):
            for entry in candidate_entries:
                relative = entry.protocol_file.relative_to(root)
                st.write(entry.label_vi)
                st.code(
                    ".\\.venv\\Scripts\\python.exe .\\scripts\\run_benchmark_corpus.py `\n"
                    f"  --corpus {str(relative).replace('/', chr(92))}",
                    language="powershell",
                )

    with st.expander("Benchmark học thuật MPV", expanded=False):
        academic = catalog.get("level_02_mpv_acceptance_v1")
        st.write(academic.description_vi)
        st.caption(
            "MPV dùng để bổ sung bằng chứng học thuật. Kết quả không được gộp với nguồn generated 1.000/500."
        )
        with st.expander("Chi tiết kỹ thuật", expanded=False):
            st.write(str(academic.protocol_file.relative_to(root)))

    with st.expander("Đánh giá tác động của repair", expanded=False):
        repair = catalog.get("level_02_repair_ab_v1")
        st.write(repair.description_vi)
        st.caption(
            "Best Fit được chạy trên cùng tập kiện trước và sau repair. Runtime được báo riêng, "
            "không đưa vào mục tiêu số container và chi phí."
        )
        with st.expander("Chi tiết kỹ thuật", expanded=False):
            st.write(str(repair.protocol_file.relative_to(root)))


def _render_benchmark_controls(
    level_id: str,
    root: Path,
    language: str,
    *,
    level_algorithms: list[str],
    default_algorithms: list[str],
    default_item_count: int,
    default_container_count: int,
    default_environment: str,
    config_overrides: dict[str, Any],
    config_path: Path,
    profile_id: str | None,
    available_item_count: int,
    physical_container_count: int,
    inventory_search_enabled: bool,
    active_data: ActiveDataContext,
) -> None:
    """Render and execute one immutable, source-bound benchmark request."""
    profile_token = f"{level_id}|{config_path.resolve()}|{profile_id or 'default'}"
    if st.session_state.get("benchmark_profile_token") != profile_token:
        for key in tuple(st.session_state):
            if key.startswith("benchmark_v2_") or key in {
                "benchmark_algorithms", "benchmark_item_count", "benchmark_seed_list",
                "benchmark_repeat_count", "benchmark_item_selection",
                "benchmark_selection_seed", "benchmark_run", "benchmark_scenario",
                "benchmark_show_saved_results", "benchmark_inventory_enabled",
                "benchmark_initial_count", "benchmark_maximum_count",
                "benchmark_auto_increase", "benchmark_runtime_mode",
                "benchmark_custom_runtime", "benchmark_repair_enabled",
                "benchmark_repair_budget", "benchmark_large_run_confirmed",
                "benchmark_fixed_container_count", "benchmark_request_signature",
                "benchmark_last_execution_signature", "benchmark_current_run_id",
                "pending_benchmark_run_id",
            }:
                st.session_state.pop(key, None)
        st.session_state["benchmark_profile_token"] = profile_token

    resolved_config = merge_config(load_config(config_path), dict(config_overrides))
    inherited = dict(resolved_config.get("container_search", {}))
    inherited_enabled = bool(inherited.get("enabled", inventory_search_enabled))
    inherited_initial = int(inherited.get("initial_used_container_count", default_container_count))
    inherited_maximum = int(inherited.get("max_used_container_count", physical_container_count))
    inherited_runtime = inherited.get("time_limit_seconds", 30.0)
    inherited_repair_config = dict(inherited.get("consolidation", {}))
    inherited_repair_enabled = bool(inherited_repair_config.get("enabled", False))
    inherited_repair_budget = float(inherited_repair_config.get("time_limit_seconds", 10.0))
    validation_reserve = float(inherited.get("validation_reserve_seconds", 2.0))
    default_items = min(max(int(default_item_count), 1), max(available_item_count, 1))
    default_initial = min(max(inherited_initial, 1), physical_container_count)
    default_maximum = min(
        max(inherited_maximum, default_initial), physical_container_count,
    )

    st.info(
        (
            f"Nguồn đang dùng chung: {available_item_count:,} kiện · kho "
            f"{physical_container_count:,} container. Benchmark và thí nghiệm đơn "
            "luôn đọc cùng nguồn này."
        ) if language == "vi" else (
            f"Shared source: {available_item_count:,} items · {physical_container_count:,} "
            "containers. Benchmark and single experiments always use this same source."
        )
    )
    with st.form("benchmark_atomic_request", border=True, clear_on_submit=False):
        algorithms = st.multiselect(
            t("benchmark_algorithms", language), level_algorithms,
            format_func=lambda value: get_algorithm(value).name_for(language),
            default=list(default_algorithms),
            key="benchmark_algorithms",
        )
        item_count = int(st.number_input(
            t("items", language), min_value=1, max_value=max(available_item_count, 1),
            value=default_items, step=1, key="benchmark_item_count",
        ))
        selection_strategy = st.selectbox(
            t("benchmark_item_selection", language), ITEM_SELECTION_STRATEGIES,
            format_func=lambda value: t(f"item_selection_{value}", language),
            index=ITEM_SELECTION_STRATEGIES.index("prefix"),
            key="benchmark_item_selection",
        )

        inventory_members = [
            value for value in algorithms
            if value in _INVENTORY_BENCHMARK_ALGORITHMS
        ]
        inventory_capable = _benchmark_inventory_supported(level_id, tuple(algorithms))
        inventory_mixed = bool(inventory_members) and len(inventory_members) != len(algorithms)
        if inventory_capable:
            # Inventory mode is part of the active experiment configuration.
            # Benchmark may vary counts and budgets, but must not silently run
            # a different search policy over the same source.
            inventory_enabled = True
            inventory_columns = st.columns(3)
            initial_count = int(inventory_columns[0].number_input(
                "Số container bắt đầu tìm" if language == "vi" else "Initial used-container count",
                min_value=1, max_value=max(physical_container_count, 1), step=1,
                value=default_initial,
                key="benchmark_initial_count",
            ))
            maximum_count = int(inventory_columns[1].number_input(
                "Số container tối đa được dùng" if language == "vi" else "Maximum used-container count",
                min_value=1, max_value=max(physical_container_count, 1), step=1,
                value=default_maximum,
                key="benchmark_maximum_count",
            ))
            auto_increase = inventory_columns[2].checkbox(
                "Tự tăng khi chưa có nghiệm" if language == "vi" else "Increase when no solution is found",
                value=bool(inherited.get("automatically_increase_container_count", True)),
                key="benchmark_auto_increase",
            )
            live_preview = None
            runtime_options = list(_BENCHMARK_RUNTIME_PRESETS)
            if not _unbounded_inventory_search_allowed():
                runtime_options.remove("Không giới hạn — local")
            runtime_mode = st.selectbox(
                "Thời gian tối đa cho mỗi thuật toán" if language == "vi" else "Runtime limit per algorithm",
                runtime_options, index=min(3, len(runtime_options) - 1),
                key="benchmark_runtime_mode",
            )
            custom_runtime = float(st.number_input(
                "Thời gian tùy chỉnh (giây)" if language == "vi" else "Custom runtime (seconds)",
                min_value=1.0, value=120.0, step=1.0, key="benchmark_custom_runtime",
            ))
            selected_runtime = _BENCHMARK_RUNTIME_PRESETS[runtime_mode]
            runtime_limit = custom_runtime if selected_runtime is _RUNTIME_UNSET else selected_runtime
            repair_enabled = st.checkbox(
                "Thử giảm thêm số container sau khi có nghiệm" if language == "vi" else
                "Improve solution after construction",
                value=inherited_repair_enabled, key="benchmark_repair_enabled",
            )
            repair_budget = inherited_repair_budget
            st.caption(
                f"Dành riêng {validation_reserve:g} giây để kiểm tra nghiệm. Kho có "
                f"{physical_container_count} container, nhưng hệ thống chỉ dùng số lượng cần thiết."
            )
        else:
            live_preview = None
            inventory_enabled = False
            initial_count = int(st.number_input(
                t("containers", language), min_value=1,
                max_value=max(physical_container_count, 1),
                value=min(default_container_count, max(physical_container_count, 1)),
                step=1, key="benchmark_fixed_container_count",
            ))
            maximum_count = initial_count
            auto_increase = False
            runtime_limit = inherited_runtime
            repair_enabled = False
            repair_budget = inherited_repair_budget
            if inventory_mixed:
                unsupported = [
                    get_algorithm(value).name_for(language)
                    for value in algorithms
                    if value not in _INVENTORY_BENCHMARK_ALGORITHMS
                ]
                st.error(
                    (
                        "Không thể trộn thuật toán tìm trong toàn bộ kho với thuật toán "
                        "chỉ chạy trên tập container cố định: " + ", ".join(unsupported)
                    ) if language == "vi" else (
                        "Inventory-aware and fixed-subset algorithms cannot be mixed: "
                        + ", ".join(unsupported)
                    )
                )
        with st.expander(
            "Thiết lập nâng cao" if language == "vi" else "Advanced settings",
            expanded=False,
        ):
            advanced_columns = st.columns(3)
            seed_text = advanced_columns[0].text_input(
                t("benchmark_seed_list", language), value="7", key="benchmark_seed_list",
            )
            repeats = int(advanced_columns[1].number_input(
                t("benchmark_repeats", language), min_value=1, max_value=20,
                value=1, step=1, key="benchmark_repeat_count",
            ))
            selection_seed = int(advanced_columns[2].number_input(
                t("benchmark_selection_seed", language), min_value=0, value=101, step=1,
                disabled=selection_strategy != "stable_random",
                key="benchmark_selection_seed",
            ))
            if inventory_capable:
                repair_budget = float(st.number_input(
                    "Ngân sách cải thiện (giây)" if language == "vi" else "Repair budget (seconds)",
                    min_value=1.0, value=max(inherited_repair_budget, 1.0), step=1.0,
                    key="benchmark_repair_budget",
                    disabled=not repair_enabled,
                ))
                st.caption(
                    f"Dành riêng {validation_reserve:g} giây cho kiểm định cuối. "
                    "Các giới hạn candidate/operator của solver vẫn được giữ."
                )
        large_run_confirmed = st.checkbox(
            "Tôi xác nhận chạy benchmark lớn hoặc không giới hạn thời gian.",
            value=False,
            key="benchmark_large_run_confirmed",
            help="Chỉ bắt buộc từ 500 kiện, tổng thời gian ước tính trên 5 phút hoặc khi bỏ giới hạn thời gian.",
        )
        applied = st.form_submit_button(
            "Kiểm tra và chạy benchmark" if language == "vi" else
            "Validate and run benchmark",
            type="primary", key="benchmark_apply",
        )

    if not applied:
        if st.session_state.get("benchmark_current_run_id"):
            st.session_state.pop("benchmark_current_run_id", None)
            st.session_state.pop("benchmark_last_execution_signature", None)
            st.session_state["benchmark_show_saved_results"] = False
        return False
    try:
        seeds = _parse_seed_text(seed_text)
        if len(algorithms) < 2:
            raise ValueError("Cần chọn ít nhất hai thuật toán để so sánh")
        if inventory_mixed:
            raise ValueError(
                "Không thể trộn thuật toán inventory-aware với thuật toán fixed-subset"
            )
        if inventory_enabled and not inventory_capable:
            raise ValueError(
                "Các thuật toán đã chọn không cùng hỗ trợ tìm kiếm trên toàn bộ kho"
            )
        benchmark_overrides = dict(config_overrides)
        if inventory_capable:
            benchmark_overrides = _benchmark_inventory_config_overrides(
                benchmark_overrides, enabled=inventory_enabled,
                initial_count=initial_count, maximum_count=maximum_count,
                automatically_increase=auto_increase,
                time_limit_seconds=runtime_limit,
                repair_enabled=repair_enabled,
                repair_budget_seconds=repair_budget,
            )
        draft = {
            "algorithms": list(algorithms), "item_count": item_count,
            "initial_count": initial_count, "maximum_count": maximum_count,
            "inventory_enabled": inventory_enabled, "runtime_limit": runtime_limit,
            "repair_enabled": repair_enabled, "repair_budget": repair_budget,
            "seeds": list(seeds), "repeats": repeats,
            "selection_strategy": selection_strategy,
            "selection_seed": selection_seed if selection_strategy == "stable_random" else None,
            "config_overrides": benchmark_overrides,
        }
        request_signature = _benchmark_request_signature({
            "level_id": level_id,
            "config_file": str(config_path.resolve()),
            "profile_id": active_data.profile_id,
            "raw_items_checksum": active_data.raw_items_checksum,
            "container_catalog_checksum": active_data.container_catalog_checksum,
            **{key: value for key, value in draft.items() if key != "config_overrides"},
        })
        previous_signature = st.session_state.get("benchmark_request_signature")
        if previous_signature != request_signature:
            for key in (
                "pending_benchmark_run_id", "benchmark_current_run_id",
                "benchmark_last_execution_signature", "benchmark_run",
                "benchmark_scenario",
            ):
                st.session_state.pop(key, None)
            st.session_state["benchmark_show_saved_results"] = False
        st.session_state["benchmark_request_signature"] = request_signature
    except Exception as exc:
        st.error(str(exc))
        return False
    blockers: list[str] = []
    try:
        provenance = get_benchmark_input_provenance(config_path, root=root)
        if provenance.raw_items_checksum != active_data.raw_items_checksum:
            blockers.append("ACTIVE_ITEM_SOURCE_MISMATCH")
        if provenance.container_catalog_checksum != active_data.container_catalog_checksum:
            blockers.append("ACTIVE_CONTAINER_SOURCE_MISMATCH")
        if provenance.config_file != str(config_path.resolve()):
            blockers.append("CONFIG_PROVENANCE_MISMATCH")
        preview = None
        if draft["inventory_enabled"]:
            if draft["initial_count"] > draft["maximum_count"]:
                blockers.append("START_EXCEEDS_MAXIMUM")
            if draft["maximum_count"] > physical_container_count:
                blockers.append("MAXIMUM_EXCEEDS_PHYSICAL_INVENTORY")
            preview = _cached_inventory_request_preview(
                str(config_path.resolve()), str(root.resolve()), draft["item_count"],
                draft["initial_count"], draft["maximum_count"],
                draft["selection_strategy"], draft["selection_seed"],
            )
            if not preview.capacity_limit_valid:
                blockers.append("CAPACITY_LIMIT_PROVEN")
        worst_case = _benchmark_worst_case_runtime_seconds(
            len(draft["algorithms"]), len(draft["seeds"]), draft["repeats"],
            draft["runtime_limit"],
        )
        st.markdown("**Yêu cầu đã nhận**" if language == "vi" else "**Request received**")
        st.info(
            f"So sánh {len(draft['algorithms'])} thuật toán với {draft['item_count']} kiện. "
            f"Nguồn đang chọn có {provenance.available_item_count} kiện và kho có "
            f"{provenance.physical_container_count} container."
        )
        with st.expander(
            "Thông tin dữ liệu để đối chiếu" if language == "vi" else "Data identity",
            expanded=False,
        ):
            st.write(f"Hồ sơ dữ liệu: {provenance.dataset_profile_id or 'mặc định'}")
            st.write(f"Cách lấy kiện: {draft['selection_strategy']}")
            if draft["selection_seed"] is not None:
                st.write(f"Mã lấy mẫu: {draft['selection_seed']}")
            st.caption(f"Dấu vân tay kiện: {provenance.raw_items_checksum}")
            st.caption(
                f"Dấu vân tay kho: {provenance.container_catalog_checksum or 'khai báo trực tiếp'}"
            )
        if preview is not None:
            capacity_columns = st.columns(4)
            capacity_columns[0].metric("Ít nhất theo tải/thể tích", preview.aggregate_lower_bound)
            capacity_columns[1].metric("Cho phép dùng tối đa", preview.max_used_container_count)
            capacity_columns[2].metric("Tổng volume (m³)", f"{preview.total_item_volume_m3:.3f}")
            capacity_columns[3].metric("Tổng tải trọng (kg)", f"{preview.total_item_weight_kg:.3f}")
            st.caption(
                f"LB volume={preview.volume_lower_bound}; LB payload={preview.payload_lower_bound}; "
                f"volume deficit={preview.volume_deficit_m3:.3f} m³; "
                f"payload deficit={preview.payload_deficit_kg:.3f} kg."
            )
        worst_case_text = "unlimited" if worst_case is None else f"{worst_case:.0f}s"
        st.caption(
            f"Mỗi thuật toán được chạy tối đa "
            f"{draft['runtime_limit'] if draft['runtime_limit'] is not None else 'không giới hạn'} giây. "
            f"Tổng thời gian xấu nhất ước tính: {worst_case_text}."
        )
        if blockers:
            st.error("Không thể chạy: " + ", ".join(blockers))
        requires_confirmation = _benchmark_requires_confirmation(
            item_count=draft["item_count"], worst_case_runtime_seconds=worst_case,
        )
        if requires_confirmation and not large_run_confirmed:
            st.warning(
                "Yêu cầu này là benchmark lớn. Hãy đánh dấu xác nhận rồi gửi lại yêu cầu."
            )
        if not blockers and (not requires_confirmation or large_run_confirmed):
            with st.spinner(t("benchmark_running", language)):
                result = execute_benchmark_comparison(
                    level_id=level_id, algorithm_ids=draft["algorithms"],
                    item_count=draft["item_count"], container_count=draft["initial_count"],
                    seeds=draft["seeds"], repeats=draft["repeats"],
                    environment=default_environment, config_path=config_path, root=root,
                    item_selection_strategy=draft["selection_strategy"],
                    item_selection_seed=draft["selection_seed"],
                    config_overrides=draft["config_overrides"],
                )
            manifest = json.loads((result.run_dir / "manifest.json").read_text(encoding="utf-8"))
            request_payload = json.loads(
                (result.run_dir / "benchmark" / "request.json").read_text(encoding="utf-8")
            )
            actual = dict(manifest.get("dataset_provenance", {}))
            if str(manifest.get("config_file")) != provenance.config_file:
                raise RuntimeError("Benchmark config provenance differs from preview")
            if actual.get("raw_items_checksum") != provenance.raw_items_checksum:
                raise RuntimeError("Benchmark item checksum differs from preview")
            if provenance.container_catalog_checksum and actual.get(
                "container_catalog_checksum"
            ) != provenance.container_catalog_checksum:
                raise RuntimeError("Benchmark container checksum differs from preview")
            scenarios = list(request_payload.get("scenarios", []))
            if not scenarios or int(scenarios[0].get("item_count", 0)) != draft["item_count"]:
                raise RuntimeError("Benchmark item count differs from preview")
            if int(scenarios[0].get("container_count", 0)) != draft["initial_count"]:
                raise RuntimeError("Benchmark initial container count differs from preview")
            expected_search = dict(draft["config_overrides"].get("container_search", {}))
            actual_search = dict(request_payload.get("config_overrides", {}).get(
                "container_search", {}
            ))
            for field in (
                "enabled", "initial_used_container_count", "max_used_container_count",
                "automatically_increase_container_count", "time_limit_seconds",
            ):
                if actual_search.get(field) != expected_search.get(field):
                    raise RuntimeError(
                        f"Benchmark container_search.{field} differs from preview"
                    )
            expected_repair = dict(expected_search.get("consolidation", {}))
            actual_repair = dict(actual_search.get("consolidation", {}))
            for field in ("enabled", "time_limit_seconds"):
                if actual_repair.get(field) != expected_repair.get(field):
                    raise RuntimeError(
                        f"Benchmark consolidation.{field} differs from preview"
                    )
            st.session_state["pending_benchmark_run_id"] = result.benchmark_id
            st.session_state["benchmark_current_run_id"] = result.benchmark_id
            st.session_state["benchmark_last_execution_signature"] = request_signature
            st.session_state["benchmark_show_saved_results"] = True
            if result.successful:
                st.success(t("benchmark_run_success", language))
            else:
                st.warning(t("benchmark_run_partial", language))
            return True
    except Exception as exc:
        st.exception(exc)
    return False


def _render_benchmark_comparison(
    level_id: str,
    root: Path,
    language: str,
    *,
    default_item_count: int,
    default_container_count: int,
    default_environment: str,
    config_overrides: dict[str, Any],
    config_path: Path,
    profile_id: str | None,
    available_item_count: int,
    physical_container_count: int,
    inventory_search_enabled: bool,
    active_data: ActiveDataContext,
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
    with st.expander(
        "So sánh tùy chỉnh" if language == "vi" else "Custom comparison",
        expanded=True,
    ):
        st.caption(
            "Tự chọn một trường hợp để thử; kết quả không làm thay đổi benchmark chuẩn."
            if language == "vi" else
            "Configure one case to explore; its result does not alter the standard benchmark."
        )
        submitted_now = _render_benchmark_controls(
            level_id, root, language,
            level_algorithms=level_algorithms,
            default_algorithms=default_algorithms,
            default_item_count=default_item_count,
            default_container_count=default_container_count,
            default_environment=default_environment,
            config_overrides=config_overrides,
            config_path=config_path,
            profile_id=profile_id,
            available_item_count=available_item_count,
            physical_container_count=physical_container_count,
            inventory_search_enabled=inventory_search_enabled,
            active_data=active_data,
        )
    if not submitted_now:
        submitted_now = False

    if level_id == "level_02":
        _render_level2_benchmark_catalog(root, language, active_data)

    current_signature_matches = (
        st.session_state.get("benchmark_last_execution_signature")
        == st.session_state.get("benchmark_request_signature")
        and bool(st.session_state.get("benchmark_current_run_id"))
    )
    show_saved_results = st.checkbox(
        (
            "Hiển thị kết quả của yêu cầu hiện tại"
            if current_signature_matches else "Xem kết quả đã lưu trước đây"
        ) if language == "vi" else (
            "Show current request result"
            if current_signature_matches else "View previously saved results"
        ),
        key="benchmark_show_saved_results",
    )
    if not show_saved_results:
        st.caption(
            "Kết quả cũ được đóng mặc định. Chỉ mở mục này khi bạn muốn xem lại lịch sử."
            if language == "vi" else
            "Saved results are collapsed by default. Open them only when reviewing history."
        )
        return

    show_all_history = st.checkbox(
        "Xem lịch sử từ nguồn dữ liệu khác" if language == "vi" else "Show history from other data sources",
        value=False,
        key="benchmark_show_all_profiles",
    )
    if show_all_history:
        st.warning(
            "Các kết quả khác nguồn chỉ dùng để xem lại; không được so sánh trực tiếp với nguồn hiện tại."
            if language == "vi" else
            "Results from other sources are for review only and must not be compared directly."
        )
    benchmarks = discover_benchmark_runs(
        level_id,
        root=root,
        limit=100,
        config_file=config_path,
        dataset_profile_id=profile_id if profile_id else None,
        expected_raw_items_checksum=active_data.raw_items_checksum,
        expected_container_catalog_checksum=active_data.container_catalog_checksum,
        include_all_profiles=show_all_history,
    )
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
            f"{benchmark_by_id[value].successful_execution_count} trên "
            f"{benchmark_by_id[value].execution_count} lượt chạy hợp lệ"
        ),
        key="benchmark_run",
    )
    selected = benchmark_by_id[selected_run_id]
    selected_is_current = (
        current_signature_matches
        and selected.run_id == st.session_state.get("benchmark_current_run_id")
    )
    if selected_is_current:
        st.success(
            "Đây là kết quả của đúng yêu cầu đang hiển thị."
            if language == "vi" else
            "This result belongs to the request currently shown."
        )
    else:
        st.warning(
            "Đây là kết quả đã lưu trước đây, không phải kết quả của các giá trị đang nhập."
            if language == "vi" else
            "This is a previously saved result, not the result of the values currently entered."
        )
    benchmark_dir = selected.run_dir / "benchmark"
    request_payload: dict[str, Any] = {}
    request_path = benchmark_dir / "request.json"
    if request_path.is_file():
        try:
            request_payload = json.loads(request_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            request_payload = {}
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
            "case_features": "case_features.csv",
            "pairwise_outcomes": "pairwise_outcomes.csv",
            "distribution": "distribution_summary.csv",
            "determinism": "determinism_evidence.csv",
            "repair_comparison": "repair_comparison.csv",
        }.items()
    }

    request_scenarios = list(
        request_payload.get("scenarios", []) or request_payload.get("cases", [])
    )
    request_scenario = request_scenarios[0] if request_scenarios else {}
    request_search = dict(
        request_payload.get("config_overrides", {}).get("container_search", {})
        or request_scenario.get("config_overrides", {}).get("container_search", {})
    )
    requested_items = int(request_scenario.get("item_count", 0) or 0)
    requested_initial = int(request_scenario.get("container_count", 0) or 0)
    requested_maximum = int(
        request_search.get("max_used_container_count", requested_initial) or requested_initial
    )
    requested_inventory_enabled = bool(request_search.get("enabled", False))
    source_items = (
        active_data.available_item_count
        if selected.raw_items_checksum == active_data.raw_items_checksum else "lịch sử"
    )
    source_containers = (
        active_data.physical_container_count
        if selected.container_catalog_checksum == active_data.container_catalog_checksum else "lịch sử"
    )
    if requested_inventory_enabled:
        request_container_text = (
            f"tìm trong toàn bộ kho · bắt đầu {requested_initial} · tối đa {requested_maximum}"
            if language == "vi" else
            f"full-inventory search · start {requested_initial} · maximum {requested_maximum}"
        )
    else:
        request_container_text = (
            f"dùng tập cố định {requested_initial} container"
            if language == "vi" else
            f"fixed set of {requested_initial} containers"
        )
    distinct_inputs = (
        int(results["input_fingerprint"].nunique())
        if "input_fingerprint" in results.columns else 0
    )
    item_scales = sorted(
        pd.to_numeric(results.get("item_count"), errors="coerce").dropna().astype(int).unique()
    )
    if selected.suite_id == "level_02_generated_1k_500_quick_v3":
        run_kind_label = "Kiểm tra nhanh" if language == "vi" else "Quick check"
    elif selected.suite_id == "level_02_generated_1k_500_canonical_v1":
        run_kind_label = "Benchmark chuẩn đầy đủ" if language == "vi" else "Full standard benchmark"
    elif selected.suite_id == "level_02_generated_1k_500_random_v2_candidate":
        run_kind_label = "Benchmark V2 — phân phối random" if language == "vi" else "Benchmark V2 — random distribution"
    elif selected.suite_id == "level_02_generated_1k_500_stress_v2_candidate":
        run_kind_label = "Benchmark V2 — tình huống khó" if language == "vi" else "Benchmark V2 — stress cases"
    elif selected.suite_id == "level_02_generated_1k_500_prefix_regression_v2":
        run_kind_label = "Benchmark V2 — hồi quy theo nguồn" if language == "vi" else "Benchmark V2 — source-order regression"
    elif selected.suite_id and "mpv" in selected.suite_id.lower():
        run_kind_label = "Benchmark học thuật MPV" if language == "vi" else "MPV academic benchmark"
    elif selected.run_type == "benchmark_corpus":
        run_kind_label = "Corpus nghiên cứu" if language == "vi" else "Research corpus"
    else:
        run_kind_label = "So sánh tùy chỉnh" if language == "vi" else "Custom comparison"
    if distinct_inputs > 1:
        st.info(
            f"{run_kind_label} · nguồn {source_items} kiện / kho {source_containers} container · "
            f"các quy mô đã chạy: {', '.join(str(value) for value in item_scales)} kiện"
        )
    else:
        st.info(
            f"{run_kind_label} · nguồn {source_items} kiện / kho {source_containers} container · "
            f"đã chọn {requested_items} kiện · {request_container_text}"
        )

    with st.expander(
        "Thông tin kỹ thuật của lần chạy" if language == "vi" else "Run technical details",
        expanded=False,
    ):
        st.caption(str(selected.run_dir))
        st.caption(f"Mã lần chạy: {selected.run_id}")
        if selected.dataset_profile_id:
            st.caption(f"Hồ sơ dữ liệu: {selected.dataset_profile_id}")
    columns = st.columns(4)
    values = (
        (t("benchmark_status", language), selected.status),
        ("Số bài kiểm tra" if language == "vi" else "Test cases", selected.case_count),
        ("Số lượt chạy" if language == "vi" else "Executions", selected.execution_count),
        (
            "Lượt chạy hợp lệ" if language == "vi" else "Valid executions",
            f"{selected.successful_execution_count}/{selected.execution_count}",
        ),
    )
    for column, (label, value) in zip(columns, values):
        column.metric(label, value)

    st.markdown(f"**{t('benchmark_summary', language)}**")
    distribution_results = results.copy()
    distribution_outcomes = derived["pairwise_outcomes"].copy()
    distribution_frame = derived["distribution"].copy()
    determinism_frame = derived["determinism"].copy()
    repair_comparison_frame = derived["repair_comparison"].copy()
    if not distribution_frame.empty and distinct_inputs > 1:
        run_evidence_label = (
            "Đây là kiểm tra nhanh 18 lượt; benchmark chuẩn 144 lượt chưa được thay thế bởi kết quả này."
            if selected.suite_id == "level_02_generated_1k_500_quick_v3" and language == "vi"
            else None
        )
        _render_distribution_dashboard(
            distribution_frame,
            distribution_outcomes,
            language,
            baseline_algorithm="extreme_point_best_fit",
            results=distribution_results,
            determinism=determinism_frame,
            run_label=run_evidence_label,
        )
        if not repair_comparison_frame.empty:
            st.markdown("**Tác động của repair**")
            st.dataframe(repair_comparison_frame, hide_index=True, width="stretch")
    else:
        _render_benchmark_dashboard(
            summary,
            results,
            language,
            ranking=derived["ranking"],
            pareto=derived["pareto"],
            milp_gaps=derived["milp_gaps"],
            pairwise=derived["pairwise"],
        )


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

    # The selected source is level-global. Algorithms and benchmark controls
    # consume this same config; changing an algorithm must never change data.
    level8_profile_id: str | None = None
    level8_profile: dict[str, Any] | None = None
    inventory_profile_id: str | None = None
    inventory_profile: dict[str, Any] | None = None
    selected_config: Path | None = None
    if level_id == "level_08":
        profiles = _level8_web_profiles(root)
        level8_profile_id = st.sidebar.selectbox(
            "Nguồn dữ liệu và kho container" if language == "vi" else "Data source and container inventory",
            tuple(profiles),
            format_func=lambda value: profiles[value][
                "label_vi" if language == "vi" else "label_en"
            ],
            key="level_08_web_profile",
        )
        level8_profile = profiles[level8_profile_id]
        selected_config = Path(str(level8_profile["config_file"]))
    elif level_id in {"level_01", "level_02"}:
        profiles = _inventory_web_profiles(root, level_id)
        profile_ids = tuple(profiles)
        default_profile_id = _default_inventory_profile_id(profiles)
        inventory_profile_id = st.sidebar.selectbox(
            "Nguồn dữ liệu và kho container" if language == "vi" else "Data source and container inventory",
            profile_ids,
            index=profile_ids.index(default_profile_id),
            format_func=lambda value: profiles[value][
                "label_vi" if language == "vi" else "label_en"
            ],
            key=f"{level_id}_inventory_profile",
        )
        inventory_profile = profiles[inventory_profile_id]
        selected_config = Path(str(inventory_profile["config_file"]))

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

    if selected_config is None:
        selected_config = level.config_for_algorithm(algorithm_id)
    config_path = root / selected_config
    config = load_config(config_path)
    active_data = resolve_active_data_context(level_id, config_path, root=root)

    inventory_summary = None
    if inventory_profile is not None:
        inventory_summary = get_container_inventory_summary(config_path, root=root)
        if not inventory_summary.ready:
            st.sidebar.error(
                "Catalog chưa sẵn sàng; không chạy solver với catalog thay thế."
                if language == "vi" else
                "The catalog is not ready; the solver will not substitute another catalog."
            )
            if inventory_profile.get("generation_command"):
                st.sidebar.code(str(inventory_profile["generation_command"]), language="powershell")
            st.sidebar.caption(str(inventory_summary.error or "Unknown catalog error"))
            st.stop()
        expected_physical = inventory_profile.get("expected_physical_container_count")
        expected_types = inventory_profile.get("expected_equivalent_type_count")
        if (
            expected_physical is not None
            and inventory_summary.physical_container_count != int(expected_physical)
        ) or (
            expected_types is not None
            and inventory_summary.equivalent_type_count != int(expected_types)
        ):
            st.sidebar.error(
                "Catalog không khớp profile đã chọn; dừng an toàn."
                if language == "vi" else
                "The catalog does not match the selected profile; stopped safely."
            )
            st.stop()

    limits = get_instance_limits(config_path, root=root)
    if (
        inventory_profile is not None
        and inventory_profile.get("expected_item_count") is not None
        and limits.available_items != int(inventory_profile["expected_item_count"])
    ):
        st.sidebar.error(
            "Nguồn item không khớp profile đã chọn; hãy sinh lại dataset theo lệnh bên trên."
            if language == "vi" else
            "The item source does not match the selected profile; regenerate the dataset."
        )
        st.stop()
    instance_defaults = config["instance"]
    instance_scope = (
        f"{level_id}:{level8_profile_id or inventory_profile_id}"
        if (level8_profile_id or inventory_profile_id) else level_id
    )
    if st.session_state.get("_instance_level_id") != instance_scope:
        st.session_state["item_count"] = int(instance_defaults["item_count"])
        st.session_state["container_count"] = int(instance_defaults["container_count"])
        st.session_state["_instance_level_id"] = instance_scope
        if level_id == "level_08":
            st.session_state["level_08_item_selection"] = "prefix"
            st.session_state["level_08_selection_seed"] = 42
        if inventory_profile is not None:
            inventory_defaults = dict(config.get("container_search", {}))
            consolidation_defaults = dict(
                inventory_defaults.get("consolidation", {})
            )
            st.session_state[f"{level_id}_inventory_search_enabled"] = bool(
                inventory_profile.get(
                    "inventory_search_default",
                    inventory_defaults.get("enabled", False),
                )
            )
            st.session_state[f"{level_id}_inventory_search_auto_increase"] = bool(
                inventory_defaults.get("automatically_increase_container_count", False)
            )
            st.session_state[f"{level_id}_inventory_search_max_count"] = int(
                inventory_defaults.get(
                    "max_used_container_count", instance_defaults["container_count"]
                )
            )
            st.session_state[f"{level_id}_inventory_repair_enabled"] = bool(
                consolidation_defaults.get("enabled", False)
            )
            configured_repair = float(
                consolidation_defaults.get("time_limit_seconds", 10.0)
            )
            repair_labels = {
                3.0: "Nhanh — 3 giây",
                10.0: "Cân bằng — 10 giây",
                30.0: "Nghiên cứu — 30 giây",
            }
            st.session_state[f"{level_id}_inventory_repair_mode"] = (
                repair_labels.get(configured_repair, "Tùy chỉnh")
            )
            st.session_state[f"{level_id}_inventory_repair_custom_seconds"] = int(
                configured_repair
            )
    level8_fixed_profile = (
        level8_profile is not None and level8_profile.get("mode") == "fixed"
    )
    item_max = min(
        limits.available_items,
        int(level8_profile.get("item_count_max", limits.available_items))
        if level8_profile is not None
        else limits.available_items,
    )
    # Streamlit can retain a value created by the previous profile. Clamp it
    # before constructing the widget so the visible value can never exceed the
    # source that will actually be prepared.
    retained_item_count = int(st.session_state.get("item_count", instance_defaults["item_count"]))
    if retained_item_count < 1 or retained_item_count > item_max:
        st.session_state["item_count"] = min(max(retained_item_count, 1), item_max)
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
    inventory_search_supported = (
        level_id in {"level_01", "level_02"}
        and algorithm_id in _INVENTORY_BENCHMARK_ALGORITHMS
    )
    inventory_search_config = dict(config.get("container_search", {}))
    inventory_search_enabled = False
    if inventory_search_supported:
        enabled_key = f"{level_id}_inventory_search_enabled"
        if enabled_key not in st.session_state:
            st.session_state[enabled_key] = bool(
                inventory_profile.get(
                    "inventory_search_default",
                    inventory_search_config.get("enabled", False),
                )
                if inventory_profile is not None
                else inventory_search_config.get("enabled", False)
            )
        inventory_search_enabled = st.sidebar.checkbox(
            (
                "Tìm container tốt nhất trong toàn bộ kho"
                if language == "vi"
                else "Search the full container inventory"
            ),
            key=enabled_key,
            help=(
                "Số container bên dưới là điểm bắt đầu; hệ thống vẫn đọc toàn bộ catalog."
                if language == "vi"
                else "The count below is the initial usage limit; the full catalog remains searchable."
            ),
        )
    container_count = int(st.sidebar.number_input(
        (
            "Số container bắt đầu tìm"
            if language == "vi" and inventory_search_enabled
            else "Initial used-container count"
            if inventory_search_enabled
            else t("containers", language)
        ),
        min_value=1,
        max_value=(
            limits.configured_containers
            if inventory_search_enabled or level_id in {"level_01", "level_02"}
            else container_max if level_id == "level_08" else None
        ),
        step=1, key="container_count",
        disabled=level8_fixed_profile,
        help=(
            "Profile cố định khóa số container; Demo nghiên cứu cho phép tối đa 10."
            if language == "vi" and level8_fixed_profile else
            "Fixed profiles lock the container count; Research demo allows up to 10."
            if level8_fixed_profile else
            f"Có {limits.configured_containers} container vật lý trong catalog; giới hạn dưới chỉ là điểm bắt đầu tìm kiếm."
            if language == "vi" else
            f"{limits.configured_containers} are explicitly configured; larger counts are deterministically extended Level 1 containers."
        ),
    ))
    inventory_search_auto_increase = False
    inventory_search_max_count = container_count
    inventory_search_time_limit: float | None = (
        None
        if inventory_search_config.get("time_limit_seconds") is None
        else float(inventory_search_config["time_limit_seconds"])
    )
    inventory_repair_enabled = False
    inventory_repair_budget = float(
        dict(inventory_search_config.get("consolidation", {})).get(
            "time_limit_seconds", 10.0,
        )
    )
    if inventory_search_enabled:
        if algorithm_id == "extreme_point_ffd":
            st.sidebar.info(
                (
                    "Best Fit là solver khuyến nghị khi ưu tiên chất lượng nghiệm; "
                    "FFD là comparator nhanh và có thể dùng nhiều container hơn."
                    if language == "vi" else
                    "Best Fit is recommended when solution quality is the priority; "
                    "FFD is a fast comparator and may use more containers."
                )
            )
        st.sidebar.caption(
            (
                f"Kho có {limits.configured_containers} physical container; solver sẽ xét catalog thay vì lấy prefix."
                if language == "vi"
                else f"The inventory has {limits.configured_containers} physical containers; the solver searches the catalog instead of a prefix."
            )
        )
        auto_increase_key = f"{level_id}_inventory_search_auto_increase"
        if auto_increase_key not in st.session_state:
            st.session_state[auto_increase_key] = bool(
                inventory_search_config.get(
                    "automatically_increase_container_count", False
                )
            )
        inventory_search_auto_increase = st.sidebar.checkbox(
            (
                "Tự tăng số container khi chưa có nghiệm"
                if language == "vi"
                else "Automatically increase the container count"
            ),
            key=auto_increase_key,
        )
        configured_maximum = max(
            container_count,
            min(
                int(inventory_search_config.get(
                    "max_used_container_count", limits.configured_containers
                )),
                limits.configured_containers,
            ),
        )
        max_count_key = f"{level_id}_inventory_search_max_count"
        retained_maximum = int(st.session_state.get(max_count_key, configured_maximum))
        st.session_state[max_count_key] = min(
            max(retained_maximum, container_count), limits.configured_containers,
        )
        inventory_search_max_count = int(st.sidebar.number_input(
            (
                "Số container tối đa được dùng"
                if language == "vi"
                else "Maximum used-container count"
            ),
            min_value=container_count,
            max_value=limits.configured_containers,
            step=1,
            key=max_count_key,
            help=(
                "Bạn có thể nhập mọi giá trị trong phạm vi kho. Đây là giới hạn tối đa, không phải số bắt buộc sử dụng."
                if language == "vi" else
                "Choose any value within the physical inventory. This is a maximum, not a required usage count."
            ),
        ))
        runtime_values = {
            "Nhanh — 15 giây": 15.0,
            "Tiêu chuẩn — 30 giây": 30.0,
            "Chuyên sâu — 60 giây": 60.0,
            "Nghiên cứu — 120 giây": 120.0,
            "Tùy chỉnh": "custom",
        }
        if _unbounded_inventory_search_allowed():
            runtime_values["Không giới hạn — nghiên cứu cục bộ"] = None
        configured_runtime = inventory_search_config.get("time_limit_seconds", 30)
        default_runtime_label = next(
            (
                label for label, value in runtime_values.items()
                if value == configured_runtime
            ),
            "Không giới hạn — nghiên cứu cục bộ"
            if configured_runtime is None and "Không giới hạn — nghiên cứu cục bộ" in runtime_values
            else "Tùy chỉnh",
        )
        runtime_key = f"{level_id}_inventory_runtime_mode"
        if runtime_key not in st.session_state:
            st.session_state[runtime_key] = default_runtime_label
        runtime_mode = st.sidebar.selectbox(
            "Giới hạn thời gian xử lý" if language == "vi" else "Search time budget",
            tuple(runtime_values),
            key=runtime_key,
            help=(
                "Deadline dùng chung cho inventory search, construction và consolidation."
                if language == "vi"
                else "One deadline covers inventory search, construction, and consolidation."
            ),
        )
        runtime_value = runtime_values[runtime_mode]
        if runtime_value == "custom":
            custom_key = f"{level_id}_inventory_runtime_custom_seconds"
            if custom_key not in st.session_state:
                st.session_state[custom_key] = int(configured_runtime or 60)
            inventory_search_time_limit = float(st.sidebar.number_input(
                "Thời gian tối đa (giây)" if language == "vi" else "Maximum runtime (seconds)",
                min_value=5,
                max_value=300,
                step=5,
                key=custom_key,
            ))
            if inventory_search_time_limit > 120:
                st.sidebar.warning(
                    "Thời gian xử lý trên 120 giây phù hợp chạy nghiên cứu cục bộ; web deploy có thể giới hạn worker."
                    if language == "vi"
                    else "Budgets above 120 seconds are intended for local research; web deployments may limit workers."
                )
        else:
            inventory_search_time_limit = runtime_value
        if inventory_search_time_limit is None:
            st.sidebar.warning(
                "Không giới hạn chỉ bỏ deadline thời gian. Giới hạn composition, candidate, item order và số container tối đa vẫn được giữ."
                if language == "vi"
                else "Unlimited removes only the time deadline. Composition, candidate, item-order, and maximum-container guards remain active."
            )
        repair_config = dict(inventory_search_config.get("consolidation", {}))
        repair_enabled_key = f"{level_id}_inventory_repair_enabled"
        if repair_enabled_key not in st.session_state:
            st.session_state[repair_enabled_key] = bool(
                repair_config.get("enabled", False)
            )
        inventory_repair_enabled = st.sidebar.checkbox(
            (
                "Cải thiện nghiệm sau construction"
                if language == "vi" else "Improve the solution after construction"
            ),
            key=repair_enabled_key,
            help=(
                "Repair có thể giảm số container hoặc chi phí nhưng không bảo đảm; "
                "timeout vẫn giữ nghiệm hợp lệ ban đầu."
                if language == "vi" else
                "Repair may reduce container count or cost but is not guaranteed; "
                "a timeout preserves the original validated solution."
            ),
        )
        repair_modes = {
            "Nhanh — 3 giây": 3.0,
            "Cân bằng — 10 giây": 10.0,
            "Nghiên cứu — 30 giây": 30.0,
            "Tùy chỉnh": "custom",
        } if language == "vi" else {
            "Fast — 3 seconds": 3.0,
            "Balanced — 10 seconds": 10.0,
            "Research — 30 seconds": 30.0,
            "Custom": "custom",
        }
        configured_repair = float(repair_config.get("time_limit_seconds", 10.0))
        default_repair_mode = next(
            (label for label, value in repair_modes.items() if value == configured_repair),
            next(reversed(repair_modes)),
        )
        repair_mode_key = f"{level_id}_inventory_repair_mode"
        if (
            repair_mode_key not in st.session_state
            or st.session_state[repair_mode_key] not in repair_modes
        ):
            st.session_state[repair_mode_key] = default_repair_mode
        repair_mode = st.sidebar.selectbox(
            "Ngân sách cải thiện" if language == "vi" else "Improvement budget",
            tuple(repair_modes),
            key=repair_mode_key,
            disabled=not inventory_repair_enabled,
        )
        requested_repair = repair_modes[repair_mode]
        if requested_repair == "custom":
            repair_custom_key = f"{level_id}_inventory_repair_custom_seconds"
            if repair_custom_key not in st.session_state:
                st.session_state[repair_custom_key] = int(configured_repair)
            requested_repair = float(st.sidebar.number_input(
                "Thời gian repair tối đa (giây)" if language == "vi" else "Maximum repair time (seconds)",
                min_value=1,
                max_value=120,
                step=1,
                key=repair_custom_key,
                disabled=not inventory_repair_enabled,
            ))
        requested_repair = float(requested_repair)
        validation_reserve = float(
            inventory_search_config.get("validation_reserve_seconds", 2.0)
        )
        inventory_repair_budget = _effective_inventory_repair_budget(
            requested_repair,
            global_time_limit_seconds=inventory_search_time_limit,
            validation_reserve_seconds=validation_reserve,
        )
        if inventory_repair_enabled and inventory_repair_budget < requested_repair:
            st.sidebar.warning(
                (
                    f"Budget repair được giới hạn còn {inventory_repair_budget:g}s "
                    "để giữ validation reserve."
                    if language == "vi" else
                    f"Repair is capped at {inventory_repair_budget:g}s to preserve "
                    "the validation reserve."
                )
            )
        if inventory_summary is not None:
            with st.sidebar.expander(
                "Tổng quan kho container" if language == "vi" else "Container inventory overview"
            ):
                st.caption(
                    (
                        f"{inventory_summary.available_container_count:,} khả dụng / "
                        f"{inventory_summary.physical_container_count:,} physical · "
                        f"{inventory_summary.equivalent_type_count} type tương đương"
                    )
                )
                st.caption(
                    (
                        f"Tổng thể tích: {inventory_summary.total_available_volume_m3:,.2f} m³ · "
                        f"Tổng tải trọng: {inventory_summary.total_available_payload_kg:,.0f} kg"
                    )
                )
                st.caption(
                    (
                        "Dấu vết kho: " + str(inventory_summary.inventory_fingerprint)
                        if language == "vi" else
                        "Inventory fingerprint: " + str(inventory_summary.inventory_fingerprint)
                    )
                )
                st.dataframe(
                    pd.DataFrame(inventory_summary.type_rows),
                    hide_index=True,
                    width="stretch",
                )
    elif inventory_summary is not None:
        st.sidebar.caption(
            (
                f"Catalog: {inventory_summary.available_container_count:,} container khả dụng · "
                f"{inventory_summary.equivalent_type_count} type tương đương"
                if language == "vi" else
                f"Catalog: {inventory_summary.available_container_count:,} available containers · "
                f"{inventory_summary.equivalent_type_count} equivalent types"
            )
        )
    if level_id == "level_08" and level8_profile is not None:
        profile_metadata = _level8_profile_metadata(
            str(level8_profile_id), level8_profile, config
        )
        comparable = profile_metadata["data_kind"] == "cross_level_comparable"
        kind_labels = {
            "cross_level_comparable": {
                "vi": "Dữ liệu so sánh liên level",
                "en": "Cross-level comparable data",
            },
            "semantic_fixture": {
                "vi": "Dữ liệu fixture ngữ nghĩa",
                "en": "Semantic fixture data",
            },
            "synthetic_research": {
                "vi": "Dữ liệu nghiên cứu synthetic",
                "en": "Synthetic research data",
            },
        }
        kind_label = kind_labels.get(
            profile_metadata["data_kind"],
            {"vi": "Dữ liệu Level 8", "en": "Level 8 data"},
        )
        st.sidebar.markdown(
            f"**{kind_label[language]}**"
        )
        st.sidebar.caption(
            f"Dataset: `{profile_metadata['dataset_id']}` · "
            f"Container catalog: `{profile_metadata['container_catalog_id']}`"
        )
        if comparable:
            st.sidebar.info(
                "Chỉ so sánh kết quả khi dataset, catalog container, checksum tập item, "
                "cách chọn và seed hoàn toàn giống nhau."
                if language == "vi"
                else "Compare results only when dataset, container catalog, selected-item "
                "checksum, selection strategy, and seed all match."
            )
        with st.sidebar.expander(
            "Thông số container" if language == "vi" else "Container specifications"
        ):
            preview = _configured_container_preview(root, config, container_count)
            if preview.empty:
                st.caption(
                    "Không có catalog container để hiển thị."
                    if language == "vi"
                    else "No container catalog is available for preview."
                )
            else:
                st.dataframe(preview, hide_index=True, width="stretch")

    item_selection_strategy = "prefix"
    item_selection_seed: int | None = None
    if level_id == "level_08" or inventory_profile is not None:
        selection_key = (
            "level_08_item_selection" if level_id == "level_08"
            else f"{level_id}_inventory_item_selection"
        )
        seed_key = (
            "level_08_selection_seed" if level_id == "level_08"
            else f"{level_id}_inventory_selection_seed"
        )
        item_selection_strategy = st.sidebar.selectbox(
            "Cách chọn items" if language == "vi" else "Item selection",
            ("prefix", "stable_random"),
            key=selection_key,
        )
        item_selection_seed = int(
            st.sidebar.number_input(
                "Seed chọn tập" if language == "vi" else "Selection seed",
                min_value=0,
                step=1,
                key=seed_key,
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
    if inventory_search_supported:
        inventory_override = _inventory_search_overrides(
            inventory_search_config,
            enabled=inventory_search_enabled,
            initial_count=container_count,
            maximum_count=inventory_search_max_count,
            automatically_increase=inventory_search_auto_increase,
            time_limit_seconds=inventory_search_time_limit,
        )
        inventory_override = _inventory_repair_overrides(
            inventory_override,
            enabled=(inventory_search_enabled and inventory_repair_enabled),
            time_limit_seconds=inventory_repair_budget,
        )
        config_overrides = {
            **config_overrides,
            "container_search": inventory_override,
        }
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
        provider_options = _routing_provider_options()
        configured_provider = str(routing_config.get("provider", "offline"))
        if configured_provider not in provider_options:
            configured_provider = "offline"
        if (
            "level_08_routing_provider" in st.session_state
            and st.session_state["level_08_routing_provider"] not in provider_options
        ):
            del st.session_state["level_08_routing_provider"]
        routing_provider = st.sidebar.selectbox(
            "Nguồn tuyến đường" if language == "vi" else "Route provider",
            provider_options,
            index=provider_options.index(configured_provider),
            key="level_08_routing_provider",
            disabled=not routing_enabled,
        )
        if routing_enabled and routing_provider == "offline":
            st.sidebar.caption(
                "Tuyến offline đi theo delivery_priority. Khoảng cách là Haversine "
                "(đường chim bay); thời gian ước tính với vận tốc 35 km/h và không phản ánh giao thông thực."
                if language == "vi"
                else "The offline route follows delivery_priority. Distance uses Haversine "
                "(straight-line); duration assumes 35 km/h and does not represent road traffic."
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
    if inventory_profile is not None:
        inventory_preview = None
        try:
            inventory_preview = get_inventory_request_preview(
                config_path,
                item_count=item_count,
                initial_used_container_count=container_count,
                max_used_container_count=inventory_search_max_count,
                item_selection_strategy=item_selection_strategy,
                item_selection_seed=(
                    item_selection_seed
                    if item_selection_strategy == "stable_random"
                    else None
                ),
                root=root,
            )
        except (OSError, ValueError) as exc:
            st.sidebar.warning(
                ("Không thể tính preview inventory: " if language == "vi" else "Cannot compute inventory preview: ")
                + str(exc)
            )
        st.sidebar.markdown(
            "**Yêu cầu sẽ thực thi**" if language == "vi" else "**Resolved request preview**"
        )
        st.sidebar.caption(
            (
                f"{item_count:,}/{limits.available_items:,} kiện khả dụng · "
                f"kho {limits.configured_containers:,} container · "
                f"bắt đầu {container_count} · tối đa {inventory_search_max_count} · "
                f"selection `{item_selection_strategy}`"
                f" · runtime `{'không giới hạn' if inventory_search_time_limit is None else f'{inventory_search_time_limit:g}s'}`"
                f" · repair `{'tắt' if not inventory_repair_enabled else f'{inventory_repair_budget:g}s'}`"
            )
            if language == "vi" else
            (
                f"{item_count:,}/{limits.available_items:,} available items · "
                f"{limits.configured_containers:,}-container inventory · "
                f"start {container_count} · maximum {inventory_search_max_count} · "
                f"selection `{item_selection_strategy}`"
                f" · runtime `{'unlimited' if inventory_search_time_limit is None else f'{inventory_search_time_limit:g}s'}`"
                f" · repair `{'off' if not inventory_repair_enabled else f'{inventory_repair_budget:g}s'}`"
            )
        )
        if inventory_preview is not None:
            def apply_sidebar_capacity_suggestion() -> None:
                st.session_state["container_count"] = int(
                    inventory_preview.aggregate_lower_bound
                )
                st.session_state[f"{level_id}_inventory_search_max_count"] = int(
                    inventory_preview.recommended_max_used_container_count
                )

            st.sidebar.button(
                "Áp dụng gợi ý số container" if language == "vi" else "Apply container suggestion",
                key=f"{level_id}_apply_inventory_suggestion",
                on_click=apply_sidebar_capacity_suggestion,
            )
            st.sidebar.caption(
                (
                    f"Lower bound: volume {inventory_preview.volume_lower_bound} · "
                    f"payload {inventory_preview.payload_lower_bound} · "
                    f"tổng hợp **{inventory_preview.aggregate_lower_bound}** · "
                    f"khuyến nghị max khoảng **{inventory_preview.recommended_max_used_container_count}**"
                )
                if language == "vi" else
                (
                    f"Lower bound: volume {inventory_preview.volume_lower_bound} · "
                    f"payload {inventory_preview.payload_lower_bound} · "
                    f"aggregate **{inventory_preview.aggregate_lower_bound}** · "
                    f"recommended max about **{inventory_preview.recommended_max_used_container_count}**"
                )
            )
            st.sidebar.caption(
                f"{inventory_preview.total_item_volume_m3:,.2f} m³ · "
                f"{inventory_preview.total_item_weight_kg:,.1f} kg · "
                f"checksum `{inventory_preview.selected_item_ids_checksum[:12]}…` · "
                f"composition khả dĩ {inventory_preview.estimated_unique_composition_count:,}"
            )
            if inventory_search_max_count < inventory_preview.recommended_max_used_container_count:
                st.sidebar.warning(
                    "Giới hạn container hiện tại khá sát lower bound; heuristic có thể không tìm được nghiệm dù tổng capacity đủ."
                    if language == "vi"
                    else "The current container limit is close to the lower bound; the heuristic may fail even when aggregate capacity is sufficient."
                )
            if not inventory_preview.capacity_limit_valid:
                st.sidebar.error(
                    (
                        "Giới hạn hiện tại chắc chắn không đủ aggregate capacity: "
                        f"thiếu {inventory_preview.volume_deficit_m3:,.3f} m³ và "
                        f"{inventory_preview.payload_deficit_kg:,.1f} kg. "
                        f"Hãy tăng tối đa lên ít nhất {inventory_preview.aggregate_lower_bound}."
                    )
                    if language == "vi" else
                    (
                        "The current limit is provably short of aggregate capacity: "
                        f"{inventory_preview.volume_deficit_m3:,.3f} m³ volume and "
                        f"{inventory_preview.payload_deficit_kg:,.1f} kg payload deficit. "
                        f"Raise the maximum to at least {inventory_preview.aggregate_lower_bound}."
                    )
                )
    run_clicked = st.sidebar.button(
        t("run", language), type="primary", width="stretch", key="run_experiment",
        disabled=exact_reference_blocked or route_input_blocked,
    )

    if run_clicked:
        # A failed request must not leave a previous successful run on screen.
        st.session_state.pop("selected_run_dir", None)
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
            config_path=config_path,
            profile_id=active_data.profile_id,
            available_item_count=limits.available_items,
            physical_container_count=(
                inventory_summary.physical_container_count
                if inventory_summary is not None else limits.configured_containers
            ),
            inventory_search_enabled=inventory_search_enabled,
            active_data=active_data,
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
