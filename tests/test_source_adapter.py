from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from container_packing.instance_data import prepare_instance
from container_packing.source_adapter import SourceAdapterError, load_csv_source


def _write_company_source(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "company_items.csv"
    source.write_text(
        "sku,length_client_mm,width_client_mm,height_client_mm,mass_client_kg,"
        "nest_group,nest_role,inside_l,inside_w,inside_h,nest_depth,nest_increment,client_note\n"
        "BOX-A,100,80,60,4,G1,host,110,90,70,3,,host note\n"
        "BOX-B,90,70,50,3,G1,child,,,,,25,child note\n",
        encoding="utf-8",
    )
    mapping = tmp_path / "company_mapping.yaml"
    mapping.write_text(
        yaml.safe_dump(
            {
                "adapter_id": "csv_column_mapping_v1",
                "source_id": "company_mock_v1",
                "columns": {
                    "id_item": ["item_code", "sku"],
                    "length": ["length_mm", "length_client_mm"],
                    "width": "width_client_mm",
                    "height": "height_client_mm",
                    "weight": "mass_client_kg",
                    "nesting_group_id": "nest_group",
                    "nesting_role": "nest_role",
                    "inner_length_mm": "inside_l",
                    "inner_width_mm": "inside_w",
                    "inner_height_mm": "inside_h",
                    "max_nesting_depth": "nest_depth",
                    "nesting_increment_height_mm": "nest_increment",
                },
                "nesting": {
                    "semantics": "incremental_height_of_item",
                    "data_source": "company_nesting_spec_v1",
                },
                "extra_columns": "preserve",
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return source, mapping


def test_company_csv_mapping_normalizes_aliases_and_preserves_extras(tmp_path: Path) -> None:
    source, mapping = _write_company_source(tmp_path)

    result = load_csv_source(source, mapping)

    assert list(result.frame["id_item"]) == ["BOX-A", "BOX-B"]
    assert result.frame.loc[0, "length"] == 100.0
    assert result.frame.loc[1, "nesting_role"] == "child"
    assert result.nesting_semantics == "incremental_height_of_item"
    assert result.nesting_data_source == "company_nesting_spec_v1"
    assert result.mapped_columns["id_item"] == "sku"
    assert result.preserved_extra_columns == ("client_note",)
    assert list(result.frame["client_note"]) == ["host note", "child note"]


def test_adapter_output_flows_through_existing_preprocessing(root: Path, tmp_path: Path) -> None:
    source, mapping = _write_company_source(tmp_path)
    config = yaml.safe_load((root / "config/level_01/default.yaml").read_text(encoding="utf-8"))
    config["instance"]["item_count"] = 2
    config["paths"]["raw_items_csv"] = str(source)
    config["paths"]["items_source_mapping"] = str(mapping)
    config["paths"]["processed_dir"] = "processed"
    config["paths"]["manifest_json"] = "processed/manifest.json"

    manifest = prepare_instance(tmp_path, config, item_count=2, container_count=2)
    items = pd.read_csv(tmp_path / manifest["items_csv"])
    saved_manifest = json.loads((tmp_path / "processed/manifest.json").read_text(encoding="utf-8"))

    assert list(items["id_item"]) == ["BOX-A", "BOX-B"]
    assert list(items["client_note"]) == ["host note", "child note"]
    assert manifest["source_adapter"]["source_id"] == "company_mock_v1"
    assert manifest["source_adapter"]["nesting_semantics"] == "incremental_height_of_item"
    assert saved_manifest["source_adapter"] == manifest["source_adapter"]


def test_tracked_level6_fixture_mapping_declares_explicit_nesting(root: Path) -> None:
    result = load_csv_source(
        root / "data/raw/level_06/declared_nesting_fixture_items.csv",
        root / "config/common/data_sources/level_06_declared_nesting_fixture.yaml",
    )

    assert list(result.frame["id_item"]) == ["HOST-001", "CHILD-001"]
    assert list(result.frame["nesting_data_source"].unique()) == [
        "synthetic_level_06_declared_nesting_fixture_v1"
    ]
    assert result.frame.loc[0, "inner_length_mm"] == "180"
    assert result.frame.loc[1, "nesting_increment_height_mm"] == "20"


def test_missing_optional_nesting_metadata_is_safe_and_undeclared(tmp_path: Path) -> None:
    source = tmp_path / "core_only.csv"
    source.write_text("sku,l,w,h,mass,extra\nA,10,9,8,1,kept\n", encoding="utf-8")
    mapping = tmp_path / "core_only.yaml"
    mapping.write_text(
        yaml.safe_dump(
            {
                "columns": {"id_item": "sku", "length": "l", "width": "w", "height": "h", "weight": "mass"},
                "nesting": {"semantics": "undeclared"},
                "extra_columns": "preserve",
            }
        ),
        encoding="utf-8",
    )

    result = load_csv_source(source, mapping)

    assert result.frame.loc[0, "nesting_role"] == "none"
    assert result.frame.loc[0, "nesting_data_source"] == "undeclared"
    assert result.preserved_extra_columns == ("extra",)


@pytest.mark.parametrize(
    ("csv_line", "mapping_columns", "message"),
    [
        ("A,10,9,8,1\nA,11,9,8,1\n", None, "duplicate item IDs"),
        ("A,0,9,8,1\n", None, "length must be a positive number"),
        ("A,10,9,8,1,invalid\n", {"nesting_role": "role"}, "nesting_role"),
        ("A,10,9,8,1,-2\n", {"inner_length_mm": "inner"}, "inner_length_mm"),
        ("A,10,9,8,1,1.5\n", {"max_nesting_depth": "depth"}, "max_nesting_depth"),
        ("A,10,9,8,1,0\n", {"nesting_increment_height_mm": "increment"}, "nesting_increment_height_mm"),
    ],
)
def test_adapter_rejects_invalid_core_and_nesting_values(
    tmp_path: Path,
    csv_line: str,
    mapping_columns: dict[str, str] | None,
    message: str,
) -> None:
    extra_header = ""
    if mapping_columns:
        extra_header = "," + next(iter(mapping_columns.values()))
    source = tmp_path / "invalid.csv"
    source.write_text(f"sku,l,w,h,mass{extra_header}\n{csv_line}", encoding="utf-8")
    columns = {"id_item": "sku", "length": "l", "width": "w", "height": "h", "weight": "mass"}
    columns.update(mapping_columns or {})
    mapping = tmp_path / "invalid_mapping.yaml"
    mapping.write_text(yaml.safe_dump({"columns": columns}), encoding="utf-8")

    with pytest.raises(SourceAdapterError, match=message):
        load_csv_source(source, mapping)


def test_adapter_rejects_missing_core_mapping_or_source_alias(tmp_path: Path) -> None:
    source = tmp_path / "items.csv"
    source.write_text("sku,l,w,h,mass\nA,10,9,8,1\n", encoding="utf-8")
    mapping = tmp_path / "mapping.yaml"
    mapping.write_text(yaml.safe_dump({"columns": {"id_item": "sku"}}), encoding="utf-8")
    with pytest.raises(SourceAdapterError, match="missing required field 'length'"):
        load_csv_source(source, mapping)

    mapping.write_text(
        yaml.safe_dump(
            {"columns": {"id_item": "sku", "length": "l", "width": "w", "height": "h", "weight": "missing"}}
        ),
        encoding="utf-8",
    )
    with pytest.raises(SourceAdapterError, match="no column for required field 'weight'"):
        load_csv_source(source, mapping)
