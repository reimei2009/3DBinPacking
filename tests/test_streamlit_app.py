import json
from pathlib import Path

from streamlit.testing.v1 import AppTest
from container_packing.web.i18n import text as t
from container_packing.web.streamlit_app import (
    _benchmark_inventory_supported,
    _benchmark_inventory_config_overrides,
    _benchmark_requires_confirmation,
    _benchmark_worst_case_runtime_seconds,
    _configured_container_preview,
    _default_inventory_profile_id,
    _effective_inventory_repair_budget,
    _level1_inventory_web_profiles,
    _inventory_repair_overrides,
    _inventory_repair_ui_qualified,
    _inventory_web_profiles,
    _inventory_search_overrides,
    _level8_profile_metadata,
    _routing_provider_options,
    _unbounded_inventory_search_allowed,
)


def test_level2_default_source_is_solver_qualified_1000_500_and_large_is_gated(
    root: Path,
) -> None:
    profiles = _inventory_web_profiles(root, "level_02")
    assert _default_inventory_profile_id(profiles) == "items_1000_fleet_500_t10"
    assert "default_catalog" in profiles
    assert "solver_research_i20000_f5000" not in profiles


def test_level3_default_source_is_qualified_inventory_and_benchmark_capable(
    root: Path,
) -> None:
    profiles = _inventory_web_profiles(root, "level_03")
    assert _default_inventory_profile_id(profiles) == "items_1000_fleet_500_t10"
    assert set(profiles) == {"default_catalog", "items_1000_fleet_500_t10"}
    assert not _inventory_repair_ui_qualified(
        "level_03", profiles["items_1000_fleet_500_t10"],
    )
    assert _benchmark_inventory_supported(
        "level_03",
        ("extreme_point_best_fit", "extreme_point_ffd", "maximal_space_best_fit"),
    )
    assert not _benchmark_inventory_supported(
        "level_03", ("extreme_point_best_fit", "milp_big_m"),
    )


def test_inventory_repair_ui_capability_is_shared_and_explicit() -> None:
    assert _inventory_repair_ui_qualified("level_01", {})
    assert _inventory_repair_ui_qualified("level_02", {})
    assert not _inventory_repair_ui_qualified("level_03", {})
    assert _inventory_repair_ui_qualified(
        "level_03", {"repair_ui_qualified": True},
    )


def test_unbounded_inventory_ui_is_guarded_on_deployment(monkeypatch) -> None:
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.delenv("ALLOW_UNBOUNDED_INVENTORY_SEARCH", raising=False)
    assert not _unbounded_inventory_search_allowed()

    monkeypatch.setenv("ALLOW_UNBOUNDED_INVENTORY_SEARCH", "true")
    assert _unbounded_inventory_search_allowed()


def test_level8_web_metadata_and_container_preview_support_comparable_data(
    root: Path,
) -> None:
    config = {
        "data_identity": {
            "profile_kind": "cross_level_comparable",
            "dataset_id": "shared_items_v1",
            "container_catalog_id": "cross_level_container_catalog_v1",
            "comparison_group_id": "level_01_to_08",
        },
        "containers": [
            {
                "container_id": "C1", "length_mm": 3000, "width_mm": 2200,
                "height_mm": 2200, "max_weight_kg": 1500, "cost": 650,
                "availability": 1,
            },
            {
                "container_id": "C2", "length_mm": 3600, "width_mm": 2300,
                "height_mm": 2300, "max_weight_kg": 2200, "cost": 760,
                "availability": 1,
            },
        ],
    }

    metadata = _level8_profile_metadata("comparable", {}, config)
    preview = _configured_container_preview(root, config, 1)

    assert metadata == {
        "profile_id": "comparable",
        "data_kind": "cross_level_comparable",
        "dataset_id": "shared_items_v1",
        "container_catalog_id": "cross_level_container_catalog_v1",
        "comparison_group_id": "level_01_to_08",
    }
    assert preview["container_id"].tolist() == ["C1"]
    assert preview.iloc[0]["volume_m3"] == 14.52


def test_level8_web_routing_hides_google_without_server_key() -> None:
    assert _routing_provider_options({}) == ("offline",)
    assert _routing_provider_options({"GOOGLE_ROUTES_API_KEY": " secret "}) == (
        "offline", "google_routes",
    )


def test_streamlit_app_runs_valid_experiment_and_renders_3d(root: Path):
    app = root / "src/container_packing/web/streamlit_app.py"
    page = AppTest.from_file(str(app), default_timeout=60).run()
    assert not page.exception
    assert [value.value for value in page.title] == ["Mô phỏng xếp container 3D"]
    tab_labels = {value.label for value in page.tabs}
    assert {
        t("result_tab", "vi"), t("benchmark_tab", "vi"),
        t("contract_tab", "vi"), t("history_tab", "vi"),
    }.issubset(tab_labels)
    assert "Chất lượng nghiệm" not in tab_labels
    selects = {value.label: value for value in page.selectbox}
    assert selects["Cấp độ"].value == "level_01"
    assert selects["Thuật toán"].options == [
        "Extreme Point — Best Fit Decreasing", "Extreme Point — First Fit Decreasing",
        "Extreme Point — Hill Climbing",
        "Extreme Point — Simulated Annealing", "Maximal Empty Spaces — Best Fit Decreasing",
        "MILP Big-M chính xác",
    ]
    next(value for value in page.selectbox if value.key == "algorithm_id").set_value(
        "extreme_point_ffd"
    ).run()
    numbers = {value.label: value for value in page.number_input}
    numbers["Số lượng kiện"].set_value(10)
    numbers["Số lượng container"].set_value(3)
    next(value for value in page.button if value.key == "run_experiment").click().run()
    assert not page.exception
    assert "Thí nghiệm hoàn tất và đã qua kiểm định độc lập." in [
        value.value for value in page.success
    ]
    metrics = {value.label: value.value for value in page.metric}
    assert metrics["Trạng thái"] == "FEASIBLE"
    assert metrics["Kiểm định"] == "VALID"
    assert metrics["Số kiện"] == "10"
    assert len(page.get("plotly_chart")) >= 1
    selects = {value.label: value for value in page.selectbox}
    assert selects["Chế độ xem 3D"].value == "C3"
    assert selects["Chế độ hiển thị"].options == ["Rõ khối", "Cân bằng", "X-Ray"]
    sliders = {value.label: value for value in page.slider}
    assert sliders["Độ đục của kiện"].value == 1.0
    assert not any(value.key == "level_02_support_threshold" for value in page.number_input)
    assert {value.label for value in page.multiselect} >= {"Ẩn các kiện"}
    item_selector = next(value for value in page.selectbox if "I0006" in value.options)
    item_selector.set_value("I0006").run()
    assert not page.exception
    assert any(value.value == "I0006" for value in page.metric)

    hidden_items = next(value for value in page.multiselect if "I0007" in value.options)
    hidden_items.set_value(["I0007"]).run()
    assert not page.exception
    assert len(page.get("plotly_chart")) >= 1


def test_level1_inventory_search_controls_are_explicit_and_opt_in(root: Path) -> None:
    app = root / "src/container_packing/web/streamlit_app.py"
    page = AppTest.from_file(str(app), default_timeout=30).run()
    page = next(
        value for value in page.selectbox if value.key == "algorithm_id"
    ).set_value("extreme_point_best_fit").run()

    profile = next(
        value for value in page.selectbox
        if value.key == "level_01_inventory_profile"
    )
    assert profile.value == "default_catalog"
    assert profile.options == [
        "Catalog cơ bản — 5 container",
        "Kho thử nghiệm — 500 container / 10 loại",
        "Kho thử nghiệm — 5.000 container / 25 loại",
    ]

    control = next(
        value for value in page.checkbox
        if value.key == "level_01_inventory_search_enabled"
    )
    assert control.value is False
    assert not any(
        value.key == "level_01_inventory_repair_enabled"
        for value in page.checkbox
    )

    page = control.set_value(True).run()

    numbers = {value.key: value for value in page.number_input}
    assert numbers["container_count"].label == "Số container bắt đầu tìm"
    assert numbers["container_count"].max == 5
    maximum = numbers["level_01_inventory_search_max_count"]
    assert maximum.label == "Số container tối đa được dùng"
    assert maximum.max == 5
    assert any(
        "solver sẽ xét catalog thay vì lấy prefix" in value.value
        for value in page.caption
    )
    runtime = next(
        value for value in page.selectbox
        if value.key == "level_01_inventory_runtime_mode"
    )
    assert runtime.options == [
        "Nhanh — 15 giây",
        "Tiêu chuẩn — 30 giây",
        "Chuyên sâu — 60 giây",
        "Nghiên cứu — 120 giây",
        "Tùy chỉnh",
        "Không giới hạn — nghiên cứu cục bộ",
    ]
    repair = next(
        value for value in page.checkbox
        if value.key == "level_01_inventory_repair_enabled"
    )
    assert repair.value is False
    repair_budget = next(
        value for value in page.selectbox
        if value.key == "level_01_inventory_repair_mode"
    )
    assert repair_budget.disabled
    page = repair.set_value(True).run()
    repair_budget = next(
        value for value in page.selectbox
        if value.key == "level_01_inventory_repair_mode"
    )
    assert not repair_budget.disabled
    assert any("repair `10s`" in value.value for value in page.caption)

    page = next(
        value for value in page.checkbox
        if value.key == "level_01_inventory_search_auto_increase"
    ).set_value(True).run()
    assert "level_01_inventory_search_max_count" in {
        value.key for value in page.number_input
    }


def test_level1_inventory_web_profiles_are_versioned(root: Path) -> None:
    profiles = _level1_inventory_web_profiles(root)

    assert set(profiles) == {
        "default_catalog", "fleet_500_t10", "fleet_5000_t25",
    }
    assert profiles["fleet_500_t10"]["expected_physical_container_count"] == 500
    assert profiles["fleet_5000_t25"]["expected_equivalent_type_count"] == 25


def test_inventory_search_ui_overlay_preserves_exact_maximum() -> None:
    resolved = _inventory_search_overrides(
        {"time_limit_seconds": 30, "max_used_container_count": 10},
        enabled=True,
        initial_count=1,
        maximum_count=5,
        automatically_increase=True,
    )

    assert resolved["initial_used_container_count"] == 1
    assert resolved["max_used_container_count"] == 5
    assert resolved["automatically_increase_container_count"] is True

    unlimited = _inventory_search_overrides(
        resolved,
        enabled=True,
        initial_count=1,
        maximum_count=5,
        automatically_increase=True,
        time_limit_seconds=None,
    )
    assert unlimited["time_limit_seconds"] is None


def test_inventory_repair_overlay_preserves_profile_settings_and_budget() -> None:
    base = {
        "validation_reserve_seconds": 2,
        "consolidation": {
            "enabled": False,
            "time_limit_seconds": 10,
            "max_candidates": 77,
            "improvement_phase_time_fractions": [0.6, 0.4],
            "container_elimination": {
                "enabled": False,
                "maximum_candidates": 88,
                "adaptive_cluster_elimination": {
                    "enabled": True,
                    "beam_width": 9,
                },
            },
        },
    }
    resolved = _inventory_repair_overrides(
        base, enabled=True, time_limit_seconds=12,
    )
    consolidation = resolved["consolidation"]
    elimination = consolidation["container_elimination"]
    assert consolidation["enabled"] is True
    assert consolidation["time_limit_seconds"] == 12
    assert consolidation["max_candidates"] == 77
    assert consolidation["improvement_phase_time_fractions"] == [0.6, 0.4]
    assert elimination["enabled"] is True
    assert elimination["maximum_candidates"] == 88
    assert elimination["adaptive_cluster_elimination"] == {
        "enabled": True, "beam_width": 9,
    }
    assert base["consolidation"]["enabled"] is False

    disabled = _inventory_repair_overrides(
        resolved, enabled=False, time_limit_seconds=3,
    )
    assert disabled["consolidation"]["enabled"] is False
    assert disabled["consolidation"]["container_elimination"]["enabled"] is False
    assert _effective_inventory_repair_budget(
        30, global_time_limit_seconds=15, validation_reserve_seconds=2,
    ) == 13
    assert _effective_inventory_repair_budget(
        30, global_time_limit_seconds=None, validation_reserve_seconds=2,
    ) == 30


def test_level2_research_inventory_profile_exposes_one_thousand_items(root: Path) -> None:
    app = root / "src/container_packing/web/streamlit_app.py"
    page = AppTest.from_file(str(app), default_timeout=60).run()
    next(value for value in page.selectbox if value.key == "level_id").set_value(
        "level_02"
    ).run()
    profile = next(
        value for value in page.selectbox if value.key == "level_02_inventory_profile"
    )
    profile.set_value("items_1000_fleet_500_t10").run()

    repair = next(
        value for value in page.checkbox
        if value.key == "level_02_inventory_repair_enabled"
    )
    assert repair.value is True
    repair_budget = next(
        value for value in page.selectbox
        if value.key == "level_02_inventory_repair_mode"
    )
    assert repair_budget.value == "Cân bằng — 10 giây"

    item_count = next(value for value in page.number_input if value.key == "item_count")
    assert item_count.max == 1000
    item_count.set_value(450).run()
    assert not page.exception
    assert next(
        value for value in page.number_input if value.key == "item_count"
    ).value == 450


def test_streamlit_exposes_same_instance_benchmark_controls(root: Path):
    app = root / "src/container_packing/web/streamlit_app.py"
    page = AppTest.from_file(str(app), default_timeout=30).run()

    assert not page.exception
    benchmark_algorithms = {value.label: value for value in page.multiselect}["Các thuật toán cần so sánh"]
    assert set(benchmark_algorithms.value) == {
        "extreme_point_ffd", "extreme_point_best_fit", "maximal_space_best_fit",
    }
    assert "Kiểm tra và chạy benchmark" in {value.label for value in page.button}
    assert "Danh sách seed" in {value.label for value in page.text_input}
    selection = {value.label: value for value in page.selectbox}["Cách chọn tập items"]
    assert selection.options == [
        "Lấy các kiện đầu tiên trong nguồn đang chọn", "Mẫu ngẫu nhiên xác định",
        "Trải đều theo thể tích", "Các items thể tích lớn nhất", "Các items nặng nhất",
        "Các kiện có khối lượng lớn so với thể tích",
    ]


def test_level2_benchmark_catalog_is_separated_for_nontechnical_users(root: Path):
    app = root / "src/container_packing/web/streamlit_app.py"
    page = AppTest.from_file(str(app), default_timeout=30).run()

    next(value for value in page.selectbox if value.key == "level_id").set_value(
        "level_02"
    ).run()
    profile = next(
        value for value in page.selectbox
        if value.key == "level_02_inventory_profile"
    )
    page = profile.set_value("items_1000_fleet_500_t10").run()

    assert not page.exception
    expander_labels = {value.label for value in page.expander}
    assert {
        "Benchmark chuẩn",
        "So sánh tùy chỉnh",
        "Benchmark học thuật MPV",
        "Đánh giá tác động của repair",
        "Benchmark V2 đang đánh giá",
    }.issubset(expander_labels)
    metric_labels = {value.label for value in page.metric}
    assert {"Nguồn dữ liệu", "Quy mô", "Số bài kiểm tra", "Tổng lượt chạy"}.issubset(
        metric_labels
    )


def test_multi_case_dashboard_explains_quality_and_hides_under_sampled_p95(
    tmp_path: Path,
) -> None:
    app = tmp_path / "benchmark_dashboard.py"
    app.write_text(
        '''
import pandas as pd
from container_packing.benchmarks.distribution import (
    build_determinism_evidence, build_distribution_summary, build_pairwise_outcomes,
)
from container_packing.web.streamlit_app import _render_distribution_dashboard

rows = []
for case_id, item_count in (("small", 20), ("large", 100)):
    for algorithm, count in (
        ("extreme_point_best_fit", 2),
        ("extreme_point_ffd", 2),
        ("maximal_space_best_fit", 1 if case_id == "small" else 3),
    ):
        for repeat in (1, 2):
            rows.append({
                "level": "level_02", "case_id": case_id,
                "scenario_id": case_id, "input_fingerprint": f"fp-{case_id}",
                "algorithm": algorithm, "success": True, "validation_valid": True,
                "objective_value": count * 1000, "used_container_count": count,
                "total_container_cost": count * 1000, "status": "FEASIBLE",
                "item_count": item_count, "aggregate_lower_bound": 1,
                "wall_runtime_seconds": float(repeat), "peak_rss_bytes": 1000,
                "random_seed": 42, "repeat": repeat,
                "placement_signature": f"{case_id}-{algorithm}",
                "item_selection_strategy": "prefix", "item_selection_seed": 0,
                "dataset_family": "generated", "scale_bucket": "test",
            })
results = pd.DataFrame(rows)
_render_distribution_dashboard(
    build_distribution_summary(results), build_pairwise_outcomes(results), "vi",
    results=results, determinism=build_determinism_evidence(results),
)
''',
        encoding="utf-8",
    )

    page = AppTest.from_file(str(app), default_timeout=30).run()

    assert not page.exception
    assert {"Kết luận", "Chất lượng", "Thời gian và tài nguyên"}.issubset(
        {value.label for value in page.tabs}
    )
    markdown = "\n".join(str(value.value) for value in page.markdown)
    captions = "\n".join(str(value.value) for value in page.caption)
    assert "Các bài tạo khác biệt" in markdown
    assert "cận dưới chưa chứng minh khả thi hình học" in captions
    assert "Chưa hiển thị p95" in captions
    assert "thời gian toàn pipeline" in captions
    assert "Rê chuột theo một quy mô" in captions
    page_text = "\n".join(
        str(value.value) for collection in (page.markdown, page.info, page.success, page.warning)
        for value in collection
    )
    assert "Maximal Empty Spaces" in page_text
    assert "DeltaGenerator" not in page_text
    assert "Creator of Delta protobuf messages" not in page_text


def test_streamlit_exposes_level4_constructive_algorithms_and_support_threshold(root: Path):
    app = root / "src/container_packing/web/streamlit_app.py"
    page = AppTest.from_file(str(app), default_timeout=30).run()

    next(value for value in page.selectbox if value.key == "level_id").set_value("level_04").run()
    algorithm = next(value for value in page.selectbox if value.key == "algorithm_id")
    assert algorithm.options == [
        "Extreme Point — Best Fit Decreasing",
        "Extreme Point — First Fit Decreasing",
        "Extreme Point — Hill Climbing",
        "Extreme Point — Simulated Annealing",
        "Maximal Empty Spaces — Best Fit Decreasing",
    ]
    assert algorithm.value == "extreme_point_best_fit"
    assert any(value.key == "level_04_support_threshold" for value in page.number_input)
    algorithm.set_value("extreme_point_simulated_annealing").run()
    numbers = {value.key: value for value in page.number_input}
    assert numbers["max_iterations"].value == 200
    assert numbers["initial_temperature"].value == 0.05
    assert numbers["cooling_rate"].value == 0.99


def test_streamlit_exposes_level5_best_fit_and_support_threshold(root: Path):
    app = root / "src/container_packing/web/streamlit_app.py"
    page = AppTest.from_file(str(app), default_timeout=30).run()

    next(value for value in page.selectbox if value.key == "level_id").set_value(
        "level_05"
    ).run()
    algorithm = next(
        value for value in page.selectbox if value.key == "algorithm_id"
    )

    assert not page.exception
    assert algorithm.options == [
        "Extreme Point — Best Fit Decreasing",
        "Extreme Point — First Fit Decreasing",
        "Extreme Point — Hill Climbing",
        "Extreme Point — Simulated Annealing",
        "Maximal Empty Spaces — Best Fit Decreasing",
    ]
    assert algorithm.value == "extreme_point_best_fit"
    assert any(
        value.key == "level_05_support_threshold" for value in page.number_input
    )
    algorithm.set_value("extreme_point_simulated_annealing").run()
    numbers = {value.key: value for value in page.number_input}
    assert numbers["max_iterations"].value == 200
    assert numbers["initial_temperature"].value == 0.05
    assert numbers["cooling_rate"].value == 0.99


def test_streamlit_runs_two_algorithm_same_instance_benchmark(root: Path):
    app = root / "src/container_packing/web/streamlit_app.py"
    page = AppTest.from_file(str(app), default_timeout=60).run()
    assert not page.exception

    next(value for value in page.multiselect if value.key == "benchmark_algorithms").set_value([
        "extreme_point_ffd", "extreme_point_best_fit",
    ])
    next(value for value in page.number_input if value.key == "benchmark_item_count").set_value(1)
    next(value for value in page.number_input if value.key == "benchmark_initial_count").set_value(2)
    next(value for value in page.number_input if value.key == "benchmark_maximum_count").set_value(2)
    next(value for value in page.text_input if value.key == "benchmark_seed_list").set_value("7")
    page = next(value for value in page.button if value.key == "benchmark_apply").click().run()

    assert not page.exception
    assert "Benchmark hoàn tất; tất cả case đều hợp lệ." in [value.value for value in page.success]
    metrics = {value.label: value.value for value in page.metric}
    assert metrics["Thuật toán hợp lệ"] == "2 trên 2"
    assert metrics["Số container ít nhất"] == "1"
    assert not any(value.key == "benchmark_scenario" for value in page.selectbox)
    assert "Từng bài kiểm tra" in {value.label for value in page.tabs}
    assert not any(value.label == "Kết quả trên nhiều bài kiểm tra" for value in page.expander)
    run_id = page.session_state["benchmark_current_run_id"]
    request = json.loads(
        (
            root / "outputs/level_01/runs" / run_id / "benchmark/request.json"
        ).read_text(encoding="utf-8")
    )
    assert request["config_overrides"]["container_search"]["enabled"] is True

    page = next(
        value for value in page.number_input if value.key == "benchmark_item_count"
    ).set_value(2).run()
    # A browser-local edit invalidates the auto-opened current result. The run
    # remains available only through the explicit history section.
    assert "benchmark_current_run_id" not in page.session_state
    assert not any(value.key == "benchmark_run" for value in page.selectbox)


def test_benchmark_runtime_guard_and_inventory_override_are_deterministic() -> None:
    base = {
        "container_search": {
            "enabled": True,
            "validation_reserve_seconds": 2,
            "max_candidates_per_count": 77,
            "consolidation": {
                "enabled": True,
                "time_limit_seconds": 10,
                "container_elimination": {"enabled": True, "maximum_candidates": 88},
            },
        },
    }
    resolved = _benchmark_inventory_config_overrides(
        base, enabled=True, initial_count=14, maximum_count=50,
        automatically_increase=True, time_limit_seconds=120,
        repair_enabled=True, repair_budget_seconds=100,
    )
    search = resolved["container_search"]
    assert search["initial_used_container_count"] == 14
    assert search["max_used_container_count"] == 50
    assert search["max_candidates_per_count"] == 77
    assert search["consolidation"]["time_limit_seconds"] == 100
    assert search["consolidation"]["container_elimination"]["maximum_candidates"] == 88
    assert _benchmark_worst_case_runtime_seconds(2, 3, 1, 120) == 720
    assert _benchmark_requires_confirmation(item_count=500, worst_case_runtime_seconds=120)
    assert _benchmark_requires_confirmation(item_count=20, worst_case_runtime_seconds=720)
    assert not _benchmark_requires_confirmation(item_count=20, worst_case_runtime_seconds=120)


def test_level2_generated_benchmark_controls_commit_500_items_and_max_50(root: Path) -> None:
    app = root / "src/container_packing/web/streamlit_app.py"
    page = AppTest.from_file(str(app), default_timeout=60).run()
    next(value for value in page.selectbox if value.key == "level_id").set_value(
        "level_02"
    ).run()
    next(
        value for value in page.selectbox
        if value.key == "level_02_inventory_profile"
    ).set_value("items_1000_fleet_500_t10").run()
    next(value for value in page.number_input if value.key == "benchmark_item_count").set_value(500)
    next(value for value in page.number_input if value.key == "benchmark_initial_count").set_value(14)
    next(value for value in page.number_input if value.key == "benchmark_maximum_count").set_value(50)
    next(value for value in page.text_input if value.key == "benchmark_seed_list").set_value("7")
    page = next(value for value in page.button if value.key == "benchmark_apply").click().run()

    assert "benchmark_v2_draft" not in page.session_state
    assert any(
        "500 kiện" in value.value and "500 container" in value.value
        for value in page.info
    )
    assert any("benchmark lớn" in value.value for value in page.warning)

    next(
        value for value in page.number_input
        if value.key == "benchmark_initial_count"
    ).set_value(10)
    next(
        value for value in page.number_input
        if value.key == "benchmark_maximum_count"
    ).set_value(10)
    page = next(
        value for value in page.button if value.key == "benchmark_apply"
    ).click().run()
    assert any("CAPACITY_LIMIT_PROVEN" in value.value for value in page.error)


def test_level2_atomic_request_persists_visible_start_and_maximum(root: Path) -> None:
    app = root / "src/container_packing/web/streamlit_app.py"
    page = AppTest.from_file(str(app), default_timeout=60).run()
    next(value for value in page.selectbox if value.key == "level_id").set_value(
        "level_02"
    ).run()
    next(
        value for value in page.selectbox
        if value.key == "level_02_inventory_profile"
    ).set_value("items_1000_fleet_500_t10").run()
    next(value for value in page.multiselect if value.key == "benchmark_algorithms").set_value([
        "extreme_point_ffd", "extreme_point_best_fit",
    ])
    next(value for value in page.number_input if value.key == "benchmark_item_count").set_value(1)
    next(value for value in page.number_input if value.key == "benchmark_initial_count").set_value(1)
    next(value for value in page.number_input if value.key == "benchmark_maximum_count").set_value(50)
    page = next(value for value in page.button if value.key == "benchmark_apply").click().run()
    assert not page.exception
    run_id = page.session_state["benchmark_current_run_id"]
    request = json.loads((
        root / "outputs/level_02/runs" / run_id / "benchmark/request.json"
    ).read_text(encoding="utf-8"))
    search = request["config_overrides"]["container_search"]
    assert request["scenarios"][0]["container_count"] == 1
    assert search["initial_used_container_count"] == 1
    assert search["max_used_container_count"] == 50
    assert search["enabled"] is True
    assert any(
        "bắt đầu 1" in value.value and "tối đa 50" in value.value
        for value in page.info
    )


def test_level2_benchmark_precheck_uses_the_atomic_submitted_values(root: Path) -> None:
    app = root / "src/container_packing/web/streamlit_app.py"
    page = AppTest.from_file(str(app), default_timeout=60).run()
    next(value for value in page.selectbox if value.key == "level_id").set_value(
        "level_02"
    ).run()
    next(
        value for value in page.selectbox
        if value.key == "level_02_inventory_profile"
    ).set_value("items_1000_fleet_500_t10").run()

    next(
        value for value in page.number_input if value.key == "benchmark_item_count"
    ).set_value(1000)
    next(
        value for value in page.number_input if value.key == "benchmark_initial_count"
    ).set_value(1)
    next(
        value for value in page.number_input if value.key == "benchmark_maximum_count"
    ).set_value(10)
    page = next(value for value in page.button if value.key == "benchmark_apply").click().run()
    metrics = {value.label: value.value for value in page.metric}
    assert metrics["Ít nhất theo tải/thể tích"] == "29"
    assert metrics["Cho phép dùng tối đa"] == "10"
    assert any("CAPACITY_LIMIT_PROVEN" in value.value for value in page.error)


def test_benchmark_blocks_mixed_inventory_and_fixed_subset_algorithms(root: Path) -> None:
    app = root / "src/container_packing/web/streamlit_app.py"
    page = AppTest.from_file(str(app), default_timeout=60).run()
    next(value for value in page.selectbox if value.key == "level_id").set_value(
        "level_02"
    ).run()
    next(
        value for value in page.multiselect if value.key == "benchmark_algorithms"
    ).set_value(["extreme_point_best_fit", "milp_big_m"])
    page = next(value for value in page.button if value.key == "benchmark_apply").click().run()

    assert any("Không thể trộn thuật toán" in value.value for value in page.error)


def test_level2_one_source_bounds_sidebar_and_benchmark_then_resets_on_switch(
    root: Path,
) -> None:
    app = root / "src/container_packing/web/streamlit_app.py"
    page = AppTest.from_file(str(app), default_timeout=60).run()
    next(value for value in page.selectbox if value.key == "level_id").set_value(
        "level_02"
    ).run()
    profile = next(
        value for value in page.selectbox
        if value.key == "level_02_inventory_profile"
    )
    page = profile.set_value("items_1000_fleet_500_t10").run()

    inputs = {value.key: value for value in page.number_input}
    assert inputs["item_count"].max == 1000
    assert inputs["container_count"].max == 500
    assert inputs["benchmark_item_count"].max == 1000
    assert inputs["benchmark_initial_count"].max == 500
    assert inputs["benchmark_maximum_count"].max == 500
    inputs["item_count"].set_value(100)
    inputs["benchmark_item_count"].set_value(1000)
    inputs["benchmark_initial_count"].set_value(29)
    inputs["benchmark_maximum_count"].set_value(50)

    profile = next(
        value for value in page.selectbox
        if value.key == "level_02_inventory_profile"
    )
    page = profile.set_value("default_catalog").run()
    inputs = {value.key: value for value in page.number_input}
    assert inputs["item_count"].max == 501
    assert inputs["container_count"].max == 5
    assert inputs["benchmark_item_count"].max == 501
    assert inputs["benchmark_item_count"].value <= 501
    assert inputs["benchmark_initial_count"].max == 5
    assert inputs["benchmark_maximum_count"].max == 5
    assert inputs["benchmark_maximum_count"].value <= 5


def test_changing_level2_algorithm_keeps_the_active_data_source(root: Path) -> None:
    app = root / "src/container_packing/web/streamlit_app.py"
    page = AppTest.from_file(str(app), default_timeout=60).run()
    next(value for value in page.selectbox if value.key == "level_id").set_value(
        "level_02"
    ).run()
    next(
        value for value in page.selectbox
        if value.key == "level_02_inventory_profile"
    ).set_value("items_1000_fleet_500_t10").run()
    before = {value.key: value for value in page.number_input}
    assert before["benchmark_item_count"].max == 1000
    assert before["benchmark_maximum_count"].max == 500

    page = next(
        value for value in page.selectbox if value.key == "algorithm_id"
    ).set_value("milp_big_m").run()
    after = {value.key: value for value in page.number_input}
    assert next(
        value for value in page.selectbox
        if value.key == "level_02_inventory_profile"
    ).value == "items_1000_fleet_500_t10"
    assert after["benchmark_item_count"].max == 1000
    assert after["benchmark_maximum_count"].max == 500


def test_streamlit_contract_renders_latex_and_switches_to_english(root: Path):
    app = root / "src/container_packing/web/streamlit_app.py"
    page = AppTest.from_file(str(app), default_timeout=30).run()
    assert not page.exception
    latex_values = [value.value for value in page.latex]
    assert any(r"\min\; B\sum_{k\in K}u_k+\sum_{k\in K}c_k u_k" in value for value in latex_values)
    assert any(r"\sum_{k\in K}a_{ik}=1\quad\forall i\in I" in value for value in latex_values)
    language = {value.label: value for value in page.selectbox}["Ngôn ngữ / Language"]
    language.set_value("English").run()
    assert not page.exception
    assert [value.value for value in page.title] == ["3D Container Packing"]
    assert any("Objective function" in value.value for value in page.markdown)


def test_streamlit_exposes_level2_support_contract(root: Path):
    app = root / "src/container_packing/web/streamlit_app.py"
    page = AppTest.from_file(str(app), default_timeout=30).run()
    level = next(value for value in page.selectbox if value.key == "level_id")
    level.set_value("level_02").run()
    assert not page.exception
    algorithms = next(value for value in page.selectbox if value.key == "algorithm_id")
    assert len(algorithms.options) == 6
    assert algorithms.value == "extreme_point_ffd"
    threshold = next(value for value in page.number_input if value.key == "level_02_support_threshold")
    assert threshold.value == 0.8
    threshold.set_value(0.9)
    next(value for value in page.number_input if value.key == "item_count").set_value(3)
    next(value for value in page.number_input if value.key == "container_count").set_value(2)
    next(value for value in page.button if value.key == "run_experiment").click().run()
    assert not page.exception
    assert any(value.value == "VALID" for value in page.metric)
    latex_values = [value.value for value in page.latex]
    assert any(r"Gf_{ik}+\sum_{j\ne i,p,q}s_{ijkpq}" in value for value in latex_values)
    assert page.info


def test_streamlit_keeps_level2_data_source_when_algorithm_changes(root: Path):
    app = root / "src/container_packing/web/streamlit_app.py"
    page = AppTest.from_file(str(app), default_timeout=30).run()
    next(value for value in page.selectbox if value.key == "level_id").set_value("level_02").run()

    catalogs = [value for value in page.selectbox if value.key == "level_02_inventory_profile"]
    assert len(catalogs) == 1
    assert any("500 container" in str(value) for value in catalogs[0].options)
    assert any("1.000 kiện" in str(value) for value in catalogs[0].options)
    assert any(value.key == "level_02_inventory_search_enabled" for value in page.checkbox)

    next(value for value in page.selectbox if value.key == "algorithm_id").set_value("milp_big_m").run()
    assert any(value.key == "level_02_inventory_profile" for value in page.selectbox)
    assert not any(value.key == "level_02_inventory_search_enabled" for value in page.checkbox)


def test_streamlit_exposes_level3_solvers_and_orientation_contract(root: Path):
    app = root / "src/container_packing/web/streamlit_app.py"
    page = AppTest.from_file(str(app), default_timeout=30).run()
    level = next(value for value in page.selectbox if value.key == "level_id")
    level.set_value("level_03").run()

    assert not page.exception
    profile = next(
        value for value in page.selectbox
        if value.key == "level_03_inventory_profile"
    )
    assert profile.value == "items_1000_fleet_500_t10"
    algorithms = next(value for value in page.selectbox if value.key == "algorithm_id")
    assert len(algorithms.options) == 3
    assert algorithms.value == "extreme_point_ffd"
    assert next(
        value for value in page.checkbox
        if value.key == "level_03_inventory_search_enabled"
    ).value is True
    numbers = {value.key: value for value in page.number_input}
    assert numbers["item_count"].max == 1000
    assert numbers["container_count"].max == 500
    assert numbers["level_03_inventory_search_max_count"].value == 23
    assert numbers["level_03_inventory_search_max_count"].max == 500
    assert numbers["benchmark_item_count"].max == 1000
    assert numbers["benchmark_initial_count"].max == 500
    assert numbers["benchmark_maximum_count"].max == 500
    assert not any(
        value.key == "level_03_inventory_repair_enabled" for value in page.checkbox
    )
    assert not any(
        value.key == "benchmark_repair_enabled" for value in page.checkbox
    )
    threshold = next(value for value in page.number_input if value.key == "level_03_support_threshold")
    assert threshold.value == 0.8
    assert any(r"\sum_{o\in O_i}r_{io}=1" in value.value for value in page.latex)


def test_streamlit_level3_profile_switch_resets_inventory_limits(root: Path) -> None:
    app = root / "src/container_packing/web/streamlit_app.py"
    page = AppTest.from_file(str(app), default_timeout=60).run()
    next(value for value in page.selectbox if value.key == "level_id").set_value(
        "level_03"
    ).run()
    profile = next(
        value for value in page.selectbox
        if value.key == "level_03_inventory_profile"
    )
    page = profile.set_value("default_catalog").run()

    assert not page.exception
    algorithms = next(value for value in page.selectbox if value.key == "algorithm_id")
    assert len(algorithms.options) == 6
    numbers = {value.key: value for value in page.number_input}
    assert numbers["item_count"].max == 501
    assert numbers["container_count"].max == 5
    assert next(
        value for value in page.checkbox
        if value.key == "level_03_inventory_search_enabled"
    ).value is False

    page = next(
        value for value in page.selectbox
        if value.key == "level_03_inventory_profile"
    ).set_value("items_1000_fleet_500_t10").run()
    numbers = {value.key: value for value in page.number_input}
    assert not page.exception
    assert numbers["item_count"].max == 1000
    assert numbers["container_count"].max == 500
    assert numbers["level_03_inventory_search_max_count"].value == 23


def test_streamlit_blocks_oversized_level3_milp_before_execution(root: Path):
    app = root / "src/container_packing/web/streamlit_app.py"
    page = AppTest.from_file(str(app), default_timeout=30).run()
    next(value for value in page.selectbox if value.key == "level_id").set_value("level_03").run()
    next(
        value for value in page.selectbox
        if value.key == "level_03_inventory_profile"
    ).set_value("default_catalog").run()
    next(value for value in page.selectbox if value.key == "algorithm_id").set_value("milp_big_m").run()
    next(value for value in page.number_input if value.key == "item_count").set_value(10).run()

    run_button = next(value for value in page.button if value.key == "run_experiment")
    assert not page.exception
    assert run_button.disabled
    assert page.warning
    assert "5" in page.warning[-1].value


def test_streamlit_allows_level3_ffd_with_ten_items(root: Path):
    app = root / "src/container_packing/web/streamlit_app.py"
    page = AppTest.from_file(str(app), default_timeout=30).run()
    next(value for value in page.selectbox if value.key == "level_id").set_value("level_03").run()
    next(value for value in page.selectbox if value.key == "algorithm_id").set_value("extreme_point_ffd").run()
    next(value for value in page.number_input if value.key == "item_count").set_value(10).run()

    run_button = next(value for value in page.button if value.key == "run_experiment")
    assert not page.exception
    assert not run_button.disabled


def test_streamlit_exposes_dynamic_level7_balance_algorithms(root: Path):
    app = root / "src/container_packing/web/streamlit_app.py"
    page = AppTest.from_file(str(app), default_timeout=30).run()
    next(value for value in page.selectbox if value.key == "level_id").set_value("level_07").run()

    assert not page.exception
    algorithm = next(value for value in page.selectbox if value.key == "algorithm_id")
    assert algorithm.options == [
        "Experimental — Balance-aware Best Fit",
        "Experimental — Balance-aware First Fit",
    ]
    next(value for value in page.number_input if value.key == "item_count").set_value(10).run()
    next(value for value in page.number_input if value.key == "container_count").set_value(3).run()
    run_button = next(value for value in page.button if value.key == "run_experiment")
    assert not run_button.disabled


def test_streamlit_exposes_level8_delivery_solvers_and_runs_tracked_demo(root: Path):
    app = root / "src/container_packing/web/streamlit_app.py"
    page = AppTest.from_file(str(app), default_timeout=60).run()

    next(value for value in page.selectbox if value.key == "level_id").set_value("level_08").run()
    algorithm = next(value for value in page.selectbox if value.key == "algorithm_id")
    assert not page.exception
    assert algorithm.options == [
        "Level 8 Best Fit giao hàng",
        "Level 8 FFD giao hàng",
    ]
    assert algorithm.value == "extreme_point_best_fit_delivery"
    item_count = next(value for value in page.number_input if value.key == "item_count")
    assert item_count.value == 6
    replay = next(value for value in page.checkbox if value.key == "level_08_sequential_replay")
    assert replay.value is True
    profile = next(
        value for value in page.selectbox if value.key == "level_08_web_profile"
    )
    assert profile.value == "quick"
    assert any("thực nghiệm" in value.value for value in page.warning)

    next(value for value in page.button if value.key == "run_experiment").click().run()
    assert not page.exception
    metrics = {value.label: value.value for value in page.metric}
    assert metrics["Trạng thái"] == "FEASIBLE"
    assert metrics["Kiểm định"] == "VALID"
    assert len(page.get("plotly_chart")) >= 3
    assert any(
        "Bản đồ giao hàng nhiều điểm" in value.value for value in page.markdown
    )


def test_streamlit_level8_profiles_reset_counts_and_cap_custom_scale(root: Path):
    app = root / "src/container_packing/web/streamlit_app.py"
    page = AppTest.from_file(str(app), default_timeout=30).run()
    next(value for value in page.selectbox if value.key == "level_id").set_value(
        "level_08"
    ).run()
    profile = next(
        value for value in page.selectbox if value.key == "level_08_web_profile"
    )
    assert profile.options == [
        "Demo logistics nhanh — fixture 6/2",
        "Demo logistics ngữ nghĩa — fixture 20/5",
        "So sánh liên level — shared data 20/5",
        "Demo nghiên cứu synthetic — tùy chỉnh",
    ]

    profile.set_value("standard").run()
    numbers = {value.key: value for value in page.number_input}
    assert numbers["item_count"].value == 20
    assert numbers["container_count"].value == 5
    assert numbers["item_count"].disabled
    assert numbers["container_count"].disabled

    profile = next(
        value for value in page.selectbox if value.key == "level_08_web_profile"
    )
    profile.set_value("comparable").run()
    numbers = {value.key: value for value in page.number_input}
    assert numbers["item_count"].value == 20
    assert numbers["container_count"].value == 5
    assert any(
        "public_3dbppsi_dataset_small_delivery_enriched_v1" in value.value
        for value in page.caption
    )

    profile = next(
        value for value in page.selectbox if value.key == "level_08_web_profile"
    )
    profile.set_value("research").run()
    numbers = {value.key: value for value in page.number_input}
    assert not numbers["item_count"].disabled
    assert not numbers["container_count"].disabled
    numbers["item_count"].set_value(100)
    numbers["container_count"].set_value(10).run()
    assert not page.exception
    assert next(
        value for value in page.selectbox if value.key == "level_08_item_selection"
    ).options == ["prefix", "stable_random"]
