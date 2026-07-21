from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_streamlit_app_runs_valid_experiment_and_renders_3d(root: Path):
    app = root / "src/container_packing/web/streamlit_app.py"
    page = AppTest.from_file(str(app), default_timeout=60).run()
    assert not page.exception
    assert [value.value for value in page.title] == ["Mô phỏng xếp container 3D — Nghiên cứu"]
    selects = {value.label: value for value in page.selectbox}
    assert selects["Cấp độ"].value == "level_01"
    assert selects["Thuật toán"].options == [
        "Extreme Point — First Fit Decreasing", "Extreme Point — Hill Climbing",
        "Extreme Point — Simulated Annealing", "MILP Big-M chính xác",
    ]
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
    assert len(page.get("plotly_chart")) == 1
    selects = {value.label: value for value in page.selectbox}
    assert selects["Chế độ xem 3D"].value == "C3"
    assert selects["Chế độ hiển thị"].options == ["Rõ khối", "Cân bằng", "X-Ray"]
    sliders = {value.label: value for value in page.slider}
    assert sliders["Độ đục của kiện"].value == 0.92
    assert {value.label for value in page.multiselect} >= {"Ẩn các kiện"}
    item_selector = next(value for value in page.selectbox if "I0006" in value.options)
    item_selector.set_value("I0006").run()
    assert not page.exception
    assert any(value.value == "I0006" for value in page.metric)

    hidden_items = next(value for value in page.multiselect if "I0007" in value.options)
    hidden_items.set_value(["I0007"]).run()
    assert not page.exception
    assert len(page.get("plotly_chart")) == 1


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
