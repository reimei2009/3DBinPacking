from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_streamlit_app_runs_valid_experiment_and_renders_3d(root: Path):
    app = root / "src/container_packing/web/streamlit_app.py"
    page = AppTest.from_file(str(app), default_timeout=60).run()
    assert not page.exception
    assert [value.value for value in page.title] == ["3D Container Packing — Research Console"]
    selects = {value.label: value for value in page.selectbox}
    assert selects["Level"].value == "level_01"
    assert selects["Algorithm"].options == [
        "extreme_point_ffd", "extreme_point_hill_climbing",
        "extreme_point_simulated_annealing", "milp_big_m",
    ]
    numbers = {value.label: value for value in page.number_input}
    numbers["Number of items"].set_value(10)
    numbers["Number of containers"].set_value(3)
    {value.label: value for value in page.button}["Run experiment"].click().run()
    assert not page.exception
    assert [value.value for value in page.success] == [
        "Experiment completed and passed independent validation."
    ]
    metrics = {value.label: value.value for value in page.metric}
    assert metrics["Status"] == "FEASIBLE"
    assert metrics["Validation"] == "VALID"
    assert metrics["Items"] == "10"
    assert len(page.get("plotly_chart")) == 1
