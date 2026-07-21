from pathlib import Path

import pytest

from container_packing.data_loader import DataValidationError, load_containers, load_items

ITEM_HEADER = "level1_order,id_item,length_mm,width_mm,height_mm,weight_kg,nesting_height_mm,stackability_code,forced_orientation,max_stackability,used_in_level1\n"
ITEM_ROW = "1,A,10,20,30,4,0,0,n,1,1\n"
CONTAINER_HEADER = "container_id,length_mm,width_mm,height_mm,max_weight_kg,availability,cost,volume_m3,data_status\n"


def write(path: Path, value: str, encoding: str = "utf-8") -> Path:
    path.write_text(value, encoding=encoding); return path


def test_reads_utf8_bom(tmp_path):
    items = load_items(write(tmp_path / "items.csv", ITEM_HEADER + ITEM_ROW, "utf-8-sig"))
    assert items[0].item_id == "A"


def test_duplicate_item_id(tmp_path):
    path = write(tmp_path / "items.csv", ITEM_HEADER + ITEM_ROW + ITEM_ROW.replace("1,A", "2,A"))
    with pytest.raises(DataValidationError, match="duplicate id_item"):
        load_items(path)


@pytest.mark.parametrize("column,value", [("length_mm", "0"), ("width_mm", "-1"), ("height_mm", "0"), ("weight_kg", "-2")])
def test_rejects_nonpositive_item_values(tmp_path, column, value):
    columns = ITEM_HEADER.strip().split(","); values = ITEM_ROW.strip().split(",")
    values[columns.index(column)] = value
    path = write(tmp_path / "items.csv", ITEM_HEADER + ",".join(values) + "\n")
    with pytest.raises(DataValidationError, match="must be > 0"):
        load_items(path)


def test_missing_column(tmp_path):
    with pytest.raises(DataValidationError, match="missing columns"):
        load_items(write(tmp_path / "items.csv", "id_item,length_mm\nA,1\n"))


def test_rejects_wrong_container_volume(tmp_path):
    row = "C,1000,1000,1000,10,1,1,2.0,synthetic_level1\n"
    with pytest.raises(DataValidationError, match="does not match dimensions"):
        load_containers(write(tmp_path / "containers.csv", CONTAINER_HEADER + row))
