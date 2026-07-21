"""Plotly adapter for the backend-neutral scene contract."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any

import plotly.graph_objects as go

from .scene_schema import validate_scene

DEFAULT_ITEM_OPACITY = 0.92
DEFAULT_DIMMED_OPACITY = 0.20

_TRIANGLE_I = (0, 1, 4, 5, 0, 1, 2, 3, 0, 2, 1, 3)
_TRIANGLE_J = (1, 3, 6, 6, 4, 4, 3, 7, 2, 6, 5, 5)
_TRIANGLE_K = (2, 2, 5, 7, 1, 5, 6, 6, 4, 4, 3, 7)
_EDGES = ((0, 1), (0, 2), (0, 4), (1, 3), (1, 5), (2, 3), (2, 6), (3, 7), (4, 5), (4, 6), (5, 7), (6, 7))
_PALETTE = (
    "#4C78A8", "#F58518", "#E45756", "#72B7B2", "#54A24B", "#EECA3B",
    "#B279A2", "#FF9DA6", "#9D755D", "#BAB0AC",
)


def stable_item_color(item_id: str) -> str:
    index = int.from_bytes(sha256(item_id.encode("utf-8")).digest()[:4], "big") % len(_PALETTE)
    return _PALETTE[index]


def _vertices(x: float, y: float, z: float, length: float, width: float, height: float):
    return (
        (x, y, z), (x + length, y, z), (x, y + width, z), (x + length, y + width, z),
        (x, y, z + height), (x + length, y, z + height),
        (x, y + width, z + height), (x + length, y + width, z + height),
    )


def _wireframe(vertices, *, name: str, color: str = "#222222", width: int = 3) -> go.Scatter3d:
    x: list[float | None] = []
    y: list[float | None] = []
    z: list[float | None] = []
    for first, second in _EDGES:
        for index in (first, second):
            x.append(vertices[index][0]); y.append(vertices[index][1]); z.append(vertices[index][2])
        x.append(None); y.append(None); z.append(None)
    return go.Scatter3d(
        x=x, y=y, z=z, mode="lines", line={"color": color, "width": width},
        name=name, hoverinfo="skip", showlegend=False,
    )


def create_figure(
    scene: dict[str, Any],
    *,
    container_id: str | None = None,
    show_labels: bool = False,
    show_boundaries: bool = True,
    language: str = "en",
    item_opacity: float = DEFAULT_ITEM_OPACITY,
    selected_item_id: str | None = None,
    dimmed_opacity: float = DEFAULT_DIMMED_OPACITY,
    hidden_item_ids: set[str] | frozenset[str] | None = None,
) -> go.Figure:
    validate_scene(scene)
    if language not in {"vi", "en"}:
        raise ValueError(f"Unsupported visualization language: {language!r}")
    if not 0.0 < item_opacity <= 1.0:
        raise ValueError(f"item_opacity must be in (0, 1], got {item_opacity}")
    if not 0.0 <= dimmed_opacity <= 1.0:
        raise ValueError(f"dimmed_opacity must be in [0, 1], got {dimmed_opacity}")
    hidden = frozenset(hidden_item_ids or ())
    labels = {
        "vi": {"container": "Container", "position": "Tọa độ", "size": "Kích thước", "weight": "Khối lượng", "volume": "thể tích", "payload": "tải trọng"},
        "en": {"container": "Container", "position": "Position", "size": "Size", "weight": "Weight", "volume": "volume", "payload": "payload"},
    }[language]
    containers = scene["containers"]
    if container_id is not None:
        containers = [value for value in containers if value["container_id"] == container_id]
        if not containers:
            raise ValueError(f"Container {container_id!r} does not exist in the scene")
    displayed_item_ids = {
        item["item_id"] for container in containers for item in container["items"]
        if item["item_id"] not in hidden
    }
    selection_active = selected_item_id in displayed_item_ids
    figure = go.Figure()
    offset_x = 0.0
    max_height = 1.0
    max_width = 1.0
    for container in containers:
        dimensions = container["dimensions_mm"]
        length = float(dimensions["length"])
        width = float(dimensions["width"])
        height = float(dimensions["height"])
        container_vertices = _vertices(offset_x, 0.0, 0.0, length, width, height)
        if show_boundaries:
            figure.add_trace(_wireframe(container_vertices, name=container["container_id"]))
        utilization = container.get("utilization", {})
        for item in container["items"]:
            if item["item_id"] in hidden:
                continue
            position = item["position_mm"]
            item_dimensions = item["dimensions_mm"]
            x = offset_x + float(position["x"])
            y = float(position["y"])
            z = float(position["z"])
            item_vertices = _vertices(
                x, y, z,
                float(item_dimensions["length"]),
                float(item_dimensions["width"]),
                float(item_dimensions["height"]),
            )
            xs, ys, zs = zip(*item_vertices)
            hover = (
                f"<b>{item['item_id']}</b><br>{labels['container']}: {container['container_id']}"
                f"<br>{labels['position']}: ({position['x']:g}, {position['y']:g}, {position['z']:g}) mm"
                f"<br>{labels['size']}: {item_dimensions['length']:g} × {item_dimensions['width']:g} × {item_dimensions['height']:g} mm"
                f"<br>{labels['weight']}: {item.get('weight_kg', 0):g} kg"
            )
            is_selected = selection_active and item["item_id"] == selected_item_id
            opacity = 1.0 if is_selected else (dimmed_opacity if selection_active else item_opacity)
            figure.add_trace(go.Mesh3d(
                x=xs, y=ys, z=zs,
                i=_TRIANGLE_I, j=_TRIANGLE_J, k=_TRIANGLE_K,
                color=stable_item_color(item["item_id"]), opacity=opacity,
                flatshading=True, name=item["item_id"], text=hover, hovertemplate="%{text}<extra></extra>",
                showscale=False, showlegend=False,
            ))
            if is_selected:
                figure.add_trace(_wireframe(
                    item_vertices, name=f"{item['item_id']} selected", color="#111111", width=7,
                ))
            if show_labels or is_selected:
                figure.add_trace(go.Scatter3d(
                    x=[x + float(item_dimensions["length"]) / 2],
                    y=[y + float(item_dimensions["width"]) / 2],
                    z=[z + float(item_dimensions["height"]) / 2],
                    mode="text", text=[item["item_id"]], textfont={"size": 10},
                    hoverinfo="skip", showlegend=False,
                ))
        volume_pct = float(utilization.get("volume_pct", 0.0))
        payload_pct = float(utilization.get("weight_pct", 0.0))
        figure.add_annotation(
            x=offset_x + length / 2, y=0, text=f"{container['container_id']} · {labels['volume']} {volume_pct:.1f}% · {labels['payload']} {payload_pct:.1f}%",
            showarrow=False, yshift=-18,
        )
        gap = max(250.0, length * 0.08)
        offset_x += length + gap
        max_height = max(max_height, height)
        max_width = max(max_width, width)
    figure.update_layout(
        title=f"{scene['level']} · {scene.get('algorithm', 'unknown algorithm')}",
        margin={"l": 0, "r": 0, "t": 45, "b": 0},
        height=720,
        scene={
            "xaxis_title": "X (mm)", "yaxis_title": "Y (mm)", "zaxis_title": "Z (mm)",
            "aspectmode": "data",
            "camera": {"eye": {"x": 1.45, "y": 1.45, "z": 1.15}},
        },
        uirevision="packing-scene",
    )
    return figure


def write_html_views(scene: dict[str, Any], output_dir: str | Path) -> tuple[Path, ...]:
    validate_scene(scene)
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    combined = destination / "combined_scene.html"
    create_figure(scene).write_html(combined, include_plotlyjs="cdn", full_html=True)
    written.append(combined)
    for container in scene["containers"]:
        path = destination / f"container_{container['container_id']}.html"
        create_figure(scene, container_id=container["container_id"]).write_html(
            path, include_plotlyjs="cdn", full_html=True
        )
        written.append(path)
    return tuple(written)
