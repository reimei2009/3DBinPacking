"""CSV source normalization for reproducible, configurable item ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import yaml


class SourceAdapterError(ValueError):
    """Raised when a configured external item source cannot be normalized."""


_CORE_COLUMNS = ("id_item", "length", "width", "height", "weight")
_OPTIONAL_DEFAULTS = {
    "nesting_height": 0.0,
    "stackability_code": "__undeclared__",
    "forced_orientation": "",
    "max_stackability": 1,
    "nesting_group_id": "",
    "nesting_role": "none",
    "inner_length_mm": "",
    "inner_width_mm": "",
    "inner_height_mm": "",
    "max_nesting_depth": "",
    "nesting_increment_height_mm": "",
    "nesting_data_source": "undeclared",
}
@dataclass(frozen=True)
class CsvSourceResult:
    frame: pd.DataFrame
    adapter_id: str
    source_id: str
    nesting_semantics: str
    nesting_data_source: str
    mapped_columns: dict[str, str | None]
    preserved_extra_columns: tuple[str, ...]


def load_csv_source(path: str | Path, mapping_path: str | Path | None = None) -> CsvSourceResult:
    """Load one CSV and normalize declared aliases into the internal staging schema."""
    source_path = Path(path)
    try:
        raw = pd.read_csv(source_path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    except (OSError, pd.errors.ParserError) as exc:
        raise SourceAdapterError(f"Cannot read CSV item source {source_path}: {exc}") from exc
    mapping = _load_mapping(mapping_path)
    columns = mapping.get("columns")
    if not isinstance(columns, dict):
        raise SourceAdapterError("CSV source mapping requires a 'columns' mapping")
    normalized_names = {str(name).casefold(): str(name) for name in raw.columns}
    mapped: dict[str, str | None] = {}
    staged: dict[str, pd.Series | object] = {}
    for field in _CORE_COLUMNS:
        if field not in columns:
            raise SourceAdapterError(f"CSV source mapping is missing required field {field!r}")
        name = _resolve_alias(columns[field], normalized_names)
        if name is None:
            raise SourceAdapterError(
                f"CSV item source {source_path} has no column for required field {field!r}; "
                f"tried aliases: {_aliases(columns[field])}"
            )
        mapped[field] = name
        staged[field] = raw[name]
    for field, default in _OPTIONAL_DEFAULTS.items():
        name = _resolve_alias(columns.get(field), normalized_names)
        mapped[field] = name
        staged[field] = raw[name] if name is not None else default
    frame = pd.DataFrame(staged)
    _validate_core(frame, source_path)
    _validate_optional(frame, source_path)
    used = {value for value in mapped.values() if value is not None}
    extras: list[str] = []
    if mapping.get("extra_columns", "preserve") == "preserve":
        reserved = set(frame.columns) | {"level1_order", "used_in_level1", "level1_note", "source_url"}
        for column in raw.columns:
            if column in used:
                continue
            target = column if column not in reserved else f"source__{column}"
            frame[target] = raw[column]
            extras.append(target)
    nesting = mapping.get("nesting", {})
    if not isinstance(nesting, dict):
        raise SourceAdapterError("CSV source mapping nesting section must be a mapping")
    semantics = str(nesting.get("semantics", "undeclared"))
    if semantics not in {"undeclared", "incremental_height_of_item"}:
        raise SourceAdapterError(
            "nesting.semantics must be 'undeclared' or 'incremental_height_of_item'"
        )
    source_id = str(mapping.get("source_id", source_path.stem)).strip() or source_path.stem
    nesting_source = str(nesting.get("data_source", "undeclared")).strip() or "undeclared"
    if semantics == "undeclared":
        frame["nesting_data_source"] = "undeclared"
    elif mapped["nesting_data_source"] is None:
        # Provenance declared by a source mapping applies to every row unless
        # the source explicitly provides a row-level provenance column.
        frame["nesting_data_source"] = nesting_source
    return CsvSourceResult(
        frame=frame,
        adapter_id=str(mapping.get("adapter_id", "csv_column_mapping_v1")),
        source_id=source_id,
        nesting_semantics=semantics,
        nesting_data_source=nesting_source,
        mapped_columns=mapped,
        preserved_extra_columns=tuple(extras),
    )


def _load_mapping(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {
            "adapter_id": "legacy_3dbppsi_implicit_v1",
            "source_id": "legacy_3dbppsi_implicit",
            "columns": {field: [field] for field in (*_CORE_COLUMNS, *_OPTIONAL_DEFAULTS)},
            "nesting": {"semantics": "undeclared", "data_source": "undeclared"},
            "extra_columns": "preserve",
        }
    mapping_path = Path(path)
    try:
        with mapping_path.open(encoding="utf-8-sig") as handle:
            value = yaml.safe_load(handle)
    except (OSError, yaml.YAMLError) as exc:
        raise SourceAdapterError(f"Cannot read CSV source mapping {mapping_path}: {exc}") from exc
    if not isinstance(value, dict):
        raise SourceAdapterError(f"CSV source mapping {mapping_path} must contain a mapping")
    return value


def _aliases(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return value
    raise SourceAdapterError("CSV column mapping entries must be strings, alias lists, or null")


def _resolve_alias(value: Any, normalized_names: dict[str, str]) -> str | None:
    for alias in _aliases(value):
        column = normalized_names.get(alias.casefold())
        if column is not None:
            return column
    return None


def _validate_core(frame: pd.DataFrame, path: Path) -> None:
    item_ids = frame["id_item"].astype(str).str.strip()
    if not bool(item_ids.all()):
        raise SourceAdapterError(f"CSV item source {path} contains an empty item ID")
    duplicates = sorted(item_ids[item_ids.duplicated(keep=False)].unique())
    if duplicates:
        raise SourceAdapterError(f"CSV item source {path} has duplicate item IDs: {', '.join(duplicates)}")
    for field in ("length", "width", "height", "weight"):
        values = pd.to_numeric(frame[field], errors="coerce")
        invalid = values.isna() | (values <= 0)
        if bool(invalid.any()):
            row = int(invalid.idxmax()) + 2
            raise SourceAdapterError(
                f"CSV item source {path}: row {row}, field {field} must be a positive number"
            )
        frame[field] = values
    frame["id_item"] = item_ids


def _validate_optional(frame: pd.DataFrame, path: Path) -> None:
    nesting_height = pd.to_numeric(frame["nesting_height"], errors="coerce")
    if bool(nesting_height.isna().any() | (nesting_height < 0).any()):
        raise SourceAdapterError(f"CSV item source {path}: nesting_height must be non-negative")
    frame["nesting_height"] = nesting_height
    roles = frame["nesting_role"].astype(str).str.strip().str.lower()
    allowed_roles = {"none", "host", "child", "both"}
    invalid_roles = ~roles.isin(allowed_roles)
    if bool(invalid_roles.any()):
        row = int(invalid_roles.idxmax()) + 2
        raise SourceAdapterError(
            f"CSV item source {path}: row {row}, nesting_role must be one of {sorted(allowed_roles)}"
        )
    frame["nesting_role"] = roles
    for field in ("inner_length_mm", "inner_width_mm", "inner_height_mm"):
        values = frame[field].astype(str).str.strip()
        supplied = values.ne("")
        numeric = pd.to_numeric(values.where(supplied), errors="coerce")
        invalid = supplied & (numeric.isna() | (numeric <= 0))
        if bool(invalid.any()):
            row = int(invalid.idxmax()) + 2
            raise SourceAdapterError(f"CSV item source {path}: row {row}, {field} must be positive when supplied")
        frame[field] = values
    depth = frame["max_nesting_depth"].astype(str).str.strip()
    supplied_depth = depth.ne("")
    numeric_depth = pd.to_numeric(depth.where(supplied_depth), errors="coerce")
    invalid_depth = supplied_depth & (numeric_depth.isna() | (numeric_depth <= 0) | (numeric_depth % 1 != 0))
    if bool(invalid_depth.any()):
        row = int(invalid_depth.idxmax()) + 2
        raise SourceAdapterError(f"CSV item source {path}: row {row}, max_nesting_depth must be a positive integer")
    increment = frame["nesting_increment_height_mm"].astype(str).str.strip()
    supplied_increment = increment.ne("")
    numeric_increment = pd.to_numeric(increment.where(supplied_increment), errors="coerce")
    invalid_increment = supplied_increment & (numeric_increment.isna() | (numeric_increment <= 0))
    if bool(invalid_increment.any()):
        row = int(invalid_increment.idxmax()) + 2
        raise SourceAdapterError(
            f"CSV item source {path}: row {row}, nesting_increment_height_mm must be positive when supplied"
        )
