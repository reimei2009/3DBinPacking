import json

import pytest

from container_packing.schemas import Container, Placement
from container_packing.visualization.plotly_3d import (
    DEFAULT_ITEM_OPACITY,
    create_figure,
    stable_item_color,
    write_html_views,
)
from container_packing.visualization.scene_schema import (
    SceneValidationError,
    build_scene,
    load_scene,
    validate_scene,
)


def _scene():
    containers = [Container("C01", 100, 80, 60, 50, 10, volume_m3=0.00048)]
    placements = [Placement("I0001", "C01", 0, 0, 0, 20, 30, 40, 5)]
    return build_scene(
        placements, containers,
        level_id="level_01", algorithm_id="extreme_point_ffd", validation_status="VALID",
    )


def _two_item_scene():
    containers = [Container("C01", 100, 80, 60, 50, 10, volume_m3=0.00048)]
    placements = [
        Placement("I0001", "C01", 0, 0, 0, 20, 30, 40, 5),
        Placement("I0002", "C01", 20, 0, 0, 15, 20, 25, 3),
    ]
    return build_scene(
        placements, containers,
        level_id="level_01", algorithm_id="extreme_point_ffd", validation_status="VALID",
    )


def test_scene_contains_versioned_geometry_and_utilization(tmp_path):
    scene = _scene()
    container = scene["containers"][0]
    assert scene["schema_version"] == "1.0"
    assert scene["coordinate_system"]["origin"] == "lower-left-back"
    assert container["utilization"]["item_count"] == 1
    assert container["utilization"]["weight_pct"] == pytest.approx(10)
    assert container["utilization"]["volume_pct"] == pytest.approx(5)
    assert scene["warnings"]["vi"].startswith("Nghiệm Level 1")
    path = tmp_path / "scene.json"
    path.write_text(json.dumps(scene), encoding="utf-8")
    assert load_scene(path) == scene


def test_scene_validation_rejects_duplicate_items():
    scene = _scene()
    scene["containers"][0]["items"].append(dict(scene["containers"][0]["items"][0]))
    with pytest.raises(SceneValidationError, match="Duplicate item_id"):
        validate_scene(scene)


def test_plotly_renderer_is_deterministic_and_exports_views(tmp_path):
    scene = _scene()
    assert stable_item_color("I0001") == stable_item_color("I0001")
    figure = create_figure(scene, show_labels=True)
    assert figure.layout.scene.aspectmode == "data"
    assert any(trace.type == "mesh3d" for trace in figure.data)
    assert next(trace for trace in figure.data if trace.type == "mesh3d").opacity == DEFAULT_ITEM_OPACITY
    paths = write_html_views(scene, tmp_path)
    assert [value.name for value in paths] == ["combined_scene.html", "container_C01.html"]
    assert all(value.stat().st_size > 1000 for value in paths)
    vietnamese = create_figure(scene, language="vi")
    assert any("Khối lượng" in str(trace.text) for trace in vietnamese.data if trace.type == "mesh3d")


def test_plotly_renderer_rejects_unknown_container():
    with pytest.raises(ValueError, match="does not exist"):
        create_figure(_scene(), container_id="missing")


def test_plotly_display_modes_highlight_and_hide_items():
    scene = _two_item_scene()
    xray = create_figure(scene, item_opacity=0.30)
    assert {trace.opacity for trace in xray.data if trace.type == "mesh3d"} == {0.30}

    highlighted = create_figure(scene, selected_item_id="I0001")
    meshes = {trace.name: trace for trace in highlighted.data if trace.type == "mesh3d"}
    assert meshes["I0001"].opacity == 1.0
    assert meshes["I0002"].opacity == 0.20
    assert any(trace.name == "I0001 selected" for trace in highlighted.data)

    hidden = create_figure(scene, hidden_item_ids={"I0002"})
    assert [trace.name for trace in hidden.data if trace.type == "mesh3d"] == ["I0001"]


@pytest.mark.parametrize("opacity", [0.0, -0.1, 1.01])
def test_plotly_renderer_rejects_invalid_item_opacity(opacity):
    with pytest.raises(ValueError, match="item_opacity"):
        create_figure(_scene(), item_opacity=opacity)
