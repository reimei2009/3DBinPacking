"""Strict CSV and YAML loaders with actionable validation errors."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import yaml

from .schemas import Container, Item, Placement

ITEM_COLUMNS = {
    "level1_order", "id_item", "length_mm", "width_mm", "height_mm",
    "weight_kg", "nesting_height_mm", "stackability_code",
    "forced_orientation", "max_stackability", "used_in_level1",
}
CONTAINER_COLUMNS = {
    "container_id", "length_mm", "width_mm", "height_mm", "max_weight_kg",
    "availability", "cost", "volume_m3", "data_status",
}
PLACEMENT_COLUMNS = {
    "item_id", "container_id", "x_mm", "y_mm", "z_mm", "length_mm",
    "width_mm", "height_mm", "weight_kg",
}


class DataValidationError(ValueError):
    """Raised when an input file violates its declared schema."""


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def merge_config(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Return a nested configuration merge without mutating either input."""
    return _deep_merge(base, override)


def load_config(path: str | Path, *, _chain: tuple[Path, ...] = ()) -> dict[str, Any]:
    config_path = Path(path)
    try:
        with config_path.open("r", encoding="utf-8-sig") as handle:
            data = yaml.safe_load(handle)
    except (OSError, yaml.YAMLError) as exc:
        raise DataValidationError(f"Cannot read config {config_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise DataValidationError(f"Config {config_path} must contain a YAML mapping")
    extends = data.pop("extends", None)
    if extends is None:
        return data
    resolved = (config_path.parent / str(extends)).resolve()
    if resolved in _chain or config_path.resolve() == resolved:
        raise DataValidationError(f"Circular config inheritance involving {resolved}")
    base = load_config(resolved, _chain=(*_chain, config_path.resolve()))
    return _deep_merge(base, data)


def _read_csv(path: str | Path, required: set[str]) -> pd.DataFrame:
    csv_path = Path(path)
    try:
        frame = pd.read_csv(csv_path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    except (OSError, pd.errors.ParserError) as exc:
        raise DataValidationError(f"Cannot read CSV {csv_path}: {exc}") from exc
    missing = sorted(required - set(frame.columns))
    if missing:
        raise DataValidationError(f"{csv_path}: missing columns: {', '.join(missing)}")
    return frame


def _number(row: pd.Series, column: str, path: Path, row_number: int, *, positive: bool = True) -> float:
    try:
        value = float(row[column])
    except (TypeError, ValueError) as exc:
        raise DataValidationError(f"{path}: row {row_number}, column {column}: invalid number {row[column]!r}") from exc
    if positive and value <= 0:
        raise DataValidationError(f"{path}: row {row_number}, column {column}: must be > 0, got {value}")
    return value


def _unique(values: Iterable[str], path: Path, column: str) -> None:
    series = pd.Series(list(values))
    duplicates = sorted(series[series.duplicated(keep=False)].unique())
    if duplicates:
        raise DataValidationError(f"{path}: duplicate {column}: {', '.join(duplicates)}")


def load_items(path: str | Path, *, limit_items: int | None = None) -> list[Item]:
    csv_path = Path(path)
    frame = _read_csv(csv_path, ITEM_COLUMNS)
    frame = frame[frame["used_in_level1"].str.lower().isin({"1", "true", "yes"})]
    if limit_items is not None:
        frame = frame.head(limit_items)
    _unique(frame["id_item"], csv_path, "id_item")
    items: list[Item] = []
    for idx, row in frame.iterrows():
        line = int(idx) + 2
        item_id = row["id_item"].strip()
        if not item_id:
            raise DataValidationError(f"{csv_path}: row {line}, column id_item: empty value")
        items.append(Item(
            item_id=item_id,
            length_mm=_number(row, "length_mm", csv_path, line),
            width_mm=_number(row, "width_mm", csv_path, line),
            height_mm=_number(row, "height_mm", csv_path, line),
            weight_kg=_number(row, "weight_kg", csv_path, line),
            level1_order=int(_number(row, "level1_order", csv_path, line, positive=False)),
            source=row.to_dict(),
        ))
    if not items:
        raise DataValidationError(f"{csv_path}: no Level 1 items found")
    return items


def load_containers(path: str | Path) -> list[Container]:
    csv_path = Path(path)
    frame = _read_csv(csv_path, CONTAINER_COLUMNS)
    _unique(frame["container_id"], csv_path, "container_id")
    containers: list[Container] = []
    for idx, row in frame.iterrows():
        line = int(idx) + 2
        length = _number(row, "length_mm", csv_path, line)
        width = _number(row, "width_mm", csv_path, line)
        height = _number(row, "height_mm", csv_path, line)
        declared_volume = _number(row, "volume_m3", csv_path, line)
        calculated_volume = length * width * height / 1_000_000_000.0
        if abs(declared_volume - calculated_volume) > 1e-6:
            raise DataValidationError(
                f"{csv_path}: row {line}, volume_m3={declared_volume} does not match dimensions ({calculated_volume})"
            )
        availability = int(_number(row, "availability", csv_path, line, positive=False))
        if availability not in (0, 1):
            raise DataValidationError(f"{csv_path}: row {line}, availability must be 0 or 1")
        containers.append(Container(
            container_id=row["container_id"].strip(), length_mm=length, width_mm=width,
            height_mm=height, max_weight_kg=_number(row, "max_weight_kg", csv_path, line),
            cost=_number(row, "cost", csv_path, line), availability=availability,
            volume_m3=declared_volume, source=row.to_dict(),
        ))
    if not containers:
        raise DataValidationError(f"{csv_path}: no containers found")
    return containers


def load_placements(path: str | Path) -> list[Placement]:
    csv_path = Path(path)
    frame = _read_csv(csv_path, PLACEMENT_COLUMNS)
    placements: list[Placement] = []
    for idx, row in frame.iterrows():
        line = int(idx) + 2
        orientation_code = row["orientation_code"].strip() if "orientation_code" in frame.columns else "XYZ"
        if not orientation_code:
            raise DataValidationError(f"{csv_path}: row {line}, column orientation_code: empty value")
        placements.append(Placement(
            item_id=row["item_id"].strip(), container_id=row["container_id"].strip(),
            x_mm=_number(row, "x_mm", csv_path, line, positive=False),
            y_mm=_number(row, "y_mm", csv_path, line, positive=False),
            z_mm=_number(row, "z_mm", csv_path, line, positive=False),
            length_mm=_number(row, "length_mm", csv_path, line),
            width_mm=_number(row, "width_mm", csv_path, line),
            height_mm=_number(row, "height_mm", csv_path, line),
            weight_kg=_number(row, "weight_kg", csv_path, line),
            orientation_code=orientation_code,
        ))
    return placements
