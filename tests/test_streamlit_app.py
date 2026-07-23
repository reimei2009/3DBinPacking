from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_streamlit_app_runs_valid_experiment_and_renders_3d(root: Path):
    app = root / "src/container_packing/web/streamlit_app.py"
    page = AppTest.from_file(str(app), default_timeout=60).run()
    assert not page.exception
    assert [value.value for value in page.title] == ["Mô phỏng xếp container 3D — Nghiên cứu"]
    tab_labels = {value.label for value in page.tabs}
    assert {
        "Kết quả và 3D", "So sánh benchmark", "Mô hình toán học", "Lịch sử chạy",
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
    {value.label: value for value in page.button}["Chạy thí nghiệm"].click().run()
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
    assert [value.value for value in page.title] == ["3D Container Packing — Research Console"]
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
