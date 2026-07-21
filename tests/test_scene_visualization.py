import json

import pytest

from container_packing.schemas import Container, Placement
from container_packing.visualization.plotly_3d import create_figure, stable_item_color, write_html_views
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
    paths = write_html_views(scene, tmp_path)
    assert [value.name for value in paths] == ["combined_scene.html", "container_C01.html"]
    assert all(value.stat().st_size > 1000 for value in paths)
    vietnamese = create_figure(scene, language="vi")
    assert any("Khối lượng" in str(trace.text) for trace in vietnamese.data if trace.type == "mesh3d")


def test_plotly_renderer_rejects_unknown_container():
    with pytest.raises(ValueError, match="does not exist"):
        create_figure(_scene(), container_id="missing")
