from pathlib import Path

from streamlit.testing.v1 import AppTest
from container_packing.web.i18n import text as t
from container_packing.web.streamlit_app import (
    _configured_container_preview,
    _level8_profile_metadata,
    _routing_provider_options,
)


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
        "Chất lượng nghiệm", "Hiệu năng", "Trade-off", "Bảng và dữ liệu",
    }.issubset(tab_labels)
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
    assert sliders["Độ đục của kiện"].value == 0.92
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

    control = next(
        value for value in page.checkbox
        if value.key == "level_01_inventory_search_enabled"
    )
    assert control.value is False

    page = control.set_value(True).run()

    numbers = {value.key: value for value in page.number_input}
    assert numbers["container_count"].label == "Số container sử dụng ban đầu"
    assert numbers["container_count"].max == 5
    assert numbers["level_01_inventory_search_max_count"].disabled
    assert any(
        "solver sẽ xét catalog thay vì lấy prefix" in value.value
        for value in page.caption
    )


def test_streamlit_exposes_same_instance_benchmark_controls(root: Path):
    app = root / "src/container_packing/web/streamlit_app.py"
    page = AppTest.from_file(str(app), default_timeout=30).run()

    assert not page.exception
    benchmark_algorithms = {value.label: value for value in page.multiselect}["Các thuật toán cần so sánh"]
    assert set(benchmark_algorithms.value) == {
        "extreme_point_ffd", "extreme_point_best_fit", "maximal_space_best_fit",
    }
    assert "Chạy benchmark so sánh" in {value.label for value in page.button}
    assert "Danh sách seed" in {value.label for value in page.text_input}
    selection = {value.label: value for value in page.selectbox}["Cách chọn tập items"]
    assert selection.options == [
        "Các dòng đầu tiên (tương thích cũ)", "Mẫu ngẫu nhiên xác định",
        "Trải đều theo thể tích", "Các items thể tích lớn nhất", "Các items nặng nhất",
    ]


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
    next(value for value in page.number_input if value.key == "benchmark_container_count").set_value(2)
    next(value for value in page.text_input if value.key == "benchmark_seed_list").set_value("7")
    next(value for value in page.button if value.key == "run_benchmark_comparison").click().run()

    assert not page.exception
    assert "Benchmark hoàn tất; tất cả case đều hợp lệ." in [value.value for value in page.success]
    metrics = {value.label: value.value for value in page.metric}
    assert metrics["Thuật toán có nghiệm"] == "2/2"
    assert metrics["Ít container nhất"] == "1"


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


def test_streamlit_exposes_level3_solvers_and_orientation_contract(root: Path):
    app = root / "src/container_packing/web/streamlit_app.py"
    page = AppTest.from_file(str(app), default_timeout=30).run()
    level = next(value for value in page.selectbox if value.key == "level_id")
    level.set_value("level_03").run()

    assert not page.exception
    algorithms = next(value for value in page.selectbox if value.key == "algorithm_id")
    assert len(algorithms.options) == 6
    assert algorithms.value == "extreme_point_ffd"
    threshold = next(value for value in page.number_input if value.key == "level_03_support_threshold")
    assert threshold.value == 0.8
    assert any(r"\sum_{o\in O_i}r_{io}=1" in value.value for value in page.latex)


def test_streamlit_blocks_oversized_level3_milp_before_execution(root: Path):
    app = root / "src/container_packing/web/streamlit_app.py"
    page = AppTest.from_file(str(app), default_timeout=30).run()
    next(value for value in page.selectbox if value.key == "level_id").set_value("level_03").run()
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
