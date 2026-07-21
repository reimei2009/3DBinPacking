"""Versioned, backend-neutral visualization scene contract."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..schemas import Container, Placement

SCENE_SCHEMA_VERSION = "1.0"
LEVEL_01_WARNING = (
    "Level 1 geometry/payload solution; rotation, support, stacking, and physical stability are not modeled."
)
LEVEL_01_WARNING_VI = (
    "Nghiệm Level 1 chỉ hợp lệ về hình học và tải trọng; chưa mô hình hóa xoay, bề mặt đỡ, chồng kiện và ổn định vật lý."
)


class SceneValidationError(ValueError):
    """Raised when a scene does not satisfy the public visualization contract."""


def build_scene(
    placements: list[Placement],
    containers: list[Container],
    *,
    level_id: str,
    algorithm_id: str,
    validation_status: str,
) -> dict[str, Any]:
    """Build a JSON-serializable scene without depending on a UI framework."""
    scene_containers: list[dict[str, Any]] = []
    for container in containers:
        group = [value for value in placements if value.container_id == container.container_id]
        if not group:
            continue
        loaded_weight = sum(value.weight_kg for value in group)
        loaded_volume = sum(value.volume_m3 for value in group)
        scene_containers.append({
            "container_id": container.container_id,
            "dimensions_mm": {
                "length": float(container.length_mm),
                "width": float(container.width_mm),
                "height": float(container.height_mm),
            },
            "capacity": {
                "max_weight_kg": float(container.max_weight_kg),
                "volume_m3": float(container.volume_m3),
                "cost": float(container.cost),
            },
            "utilization": {
                "item_count": len(group),
                "loaded_weight_kg": loaded_weight,
                "loaded_volume_m3": loaded_volume,
                "weight_pct": 100.0 * loaded_weight / container.max_weight_kg,
                "volume_pct": 100.0 * loaded_volume / container.volume_m3,
            },
            "items": [{
                "item_id": item.item_id,
                "position_mm": {"x": float(item.x_mm), "y": float(item.y_mm), "z": float(item.z_mm)},
                "dimensions_mm": {
                    "length": float(item.length_mm),
                    "width": float(item.width_mm),
                    "height": float(item.height_mm),
                },
                "weight_kg": float(item.weight_kg),
                "orientation": "fixed",
                "metadata": {},
            } for item in group],
        })
    scene = {
        "schema_version": SCENE_SCHEMA_VERSION,
        "coordinate_system": {"unit": "mm", "origin": "lower-left-back", "axes": ["x", "y", "z"]},
        "level": level_id,
        "algorithm": algorithm_id,
        "validation_status": validation_status,
        "warning": LEVEL_01_WARNING if level_id == "level_01" else "Refer to the active level contract.",
        "warnings": {
            "vi": LEVEL_01_WARNING_VI if level_id == "level_01" else "Xem contract của level đang hoạt động.",
            "en": LEVEL_01_WARNING if level_id == "level_01" else "Refer to the active level contract.",
        },
        "containers": scene_containers,
    }
    validate_scene(scene)
    return scene


def _positive_number(value: Any, path: str) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise SceneValidationError(f"{path} must be a positive number, got {value!r}")


def validate_scene(scene: dict[str, Any]) -> None:
    if not isinstance(scene, dict):
        raise SceneValidationError("Scene root must be an object")
    if scene.get("schema_version") != SCENE_SCHEMA_VERSION:
        raise SceneValidationError(
            f"Unsupported scene schema {scene.get('schema_version')!r}; expected {SCENE_SCHEMA_VERSION!r}"
        )
    if not isinstance(scene.get("level"), str) or not scene["level"]:
        raise SceneValidationError("Scene level must be a non-empty string")
    containers = scene.get("containers")
    if not isinstance(containers, list):
        raise SceneValidationError("Scene containers must be a list")
    container_ids: set[str] = set()
    item_ids: set[str] = set()
    for container_index, container in enumerate(containers):
        if not isinstance(container, dict):
            raise SceneValidationError(f"containers[{container_index}] must be an object")
        container_id = container.get("container_id")
        if not isinstance(container_id, str) or not container_id:
            raise SceneValidationError(f"containers[{container_index}].container_id must be non-empty")
        if container_id in container_ids:
            raise SceneValidationError(f"Duplicate container_id {container_id!r}")
        container_ids.add(container_id)
        dimensions = container.get("dimensions_mm", {})
        for axis in ("length", "width", "height"):
            _positive_number(dimensions.get(axis), f"{container_id}.dimensions_mm.{axis}")
        items = container.get("items")
        if not isinstance(items, list):
            raise SceneValidationError(f"{container_id}.items must be a list")
        for item_index, item in enumerate(items):
            item_id = item.get("item_id") if isinstance(item, dict) else None
            if not isinstance(item_id, str) or not item_id:
                raise SceneValidationError(f"{container_id}.items[{item_index}].item_id must be non-empty")
            if item_id in item_ids:
                raise SceneValidationError(f"Duplicate item_id {item_id!r}")
            item_ids.add(item_id)
            position = item.get("position_mm", {})
            for axis in ("x", "y", "z"):
                value = position.get(axis)
                if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
                    raise SceneValidationError(f"{item_id}.position_mm.{axis} must be non-negative")
            item_dimensions = item.get("dimensions_mm", {})
            for axis in ("length", "width", "height"):
                _positive_number(item_dimensions.get(axis), f"{item_id}.dimensions_mm.{axis}")


def load_scene(path: str | Path) -> dict[str, Any]:
    scene_path = Path(path)
    try:
        payload = json.loads(scene_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SceneValidationError(f"Cannot load scene {scene_path}: {exc}") from exc
    validate_scene(payload)
    return payload
