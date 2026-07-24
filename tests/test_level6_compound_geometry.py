from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from container_packing.data_loader import load_config
from container_packing.levels.level_06_compound_validation import validate_compound_geometry
from container_packing.levels.nesting_engine import NestingRelation
from container_packing.schemas import Container, Item, Placement


def _item(item_id: str, length: float, width: float, height: float, weight: float, **source: object) -> Item:
    return Item(item_id, length, width, height, weight, source=dict(source))


def _fixture(*, standalone_x: float = 0, standalone_z: float = 100) -> tuple[list[Item], list[Container], list[Placement], list[NestingRelation]]:
    items = [
        _item("HOST", 100, 90, 80, 10, nesting_group_id="G1", nesting_role="host", inner_length_mm="110", inner_width_mm="100", inner_height_mm="90", max_nesting_depth="1", nesting_data_source="fixture_v1"),
        _item("CHILD", 100, 90, 70, 15, nesting_group_id="G1", nesting_role="child", nesting_increment_height_mm="20", nesting_data_source="fixture_v1"),
        _item("TOP", 100, 90, 40, 5),
    ]
    containers = [Container("C1", 250, 120, 200, 1000, 1, volume_m3=0.006)]
    placements = [
        Placement("HOST", "C1", 0, 0, 0, 100, 90, 80, 10, "XYZ"),
        Placement("CHILD", "C1", 0, 0, 80, 100, 90, 70, 15, "XYZ"),
        Placement("TOP", "C1", standalone_x, 0, standalone_z, 100, 90, 40, 5, "XYZ"),
    ]
    return items, containers, placements, [NestingRelation("HOST", "CHILD", "C1")]


def _validate(root: Path, items, containers, placements, relations):
    rules = load_config(root / "config/level_06/nesting_rules.yaml")
    return validate_compound_geometry(items, containers, placements, relations, rules, support_threshold=0.8, support_epsilon_mm=1e-4)


def test_compound_geometry_uses_effective_root_height_for_exact_support(root: Path) -> None:
    items, containers, placements, relations = _fixture()
    checked = _validate(root, items, containers, placements, relations)

    assert checked.result.valid
    records = {record.root_item_id: record for record in checked.support_records}
    assert records["HOST"].is_on_floor
    assert records["TOP"].supporting_root_item_ids == ("HOST",)
    assert records["TOP"].exact_support_ratio == 1.0
    compound = next(value for value in checked.projection.compounds if value.root_item_id == "HOST")
    assert compound.effective_height_mm == 100
    assert compound.external_weight_kg == 25


def test_effective_height_can_fail_boundary_even_when_root_raw_height_fits(root: Path) -> None:
    items, containers, placements, relations = _fixture()
    containers[0] = Container("C1", 250, 120, 95, 1000, 1, volume_m3=0.00285)
    checked = _validate(root, items, containers, placements, relations)

    assert not checked.result.valid
    assert "COMPOUND_OUT_OF_BOUNDS" in {issue.code for issue in checked.result.issues}


def test_compound_overlap_is_detected_using_envelopes_not_raw_child_boxes(root: Path) -> None:
    items, containers, placements, relations = _fixture(standalone_x=50, standalone_z=50)
    checked = _validate(root, items, containers, placements, relations)

    assert not checked.result.valid
    assert "COMPOUND_OVERLAP" in {issue.code for issue in checked.result.issues}


def test_compound_support_requires_area_ratio_and_base_center(root: Path) -> None:
    items, containers, placements, relations = _fixture(standalone_x=60)
    checked = _validate(root, items, containers, placements, relations)

    codes = {issue.code for issue in checked.result.issues}
    assert "COMPOUND_INSUFFICIENT_SUPPORT_RATIO" in codes
    assert "COMPOUND_CENTER_NOT_SUPPORTED" in codes


def test_compound_validator_keeps_runtime_inactive(root: Path) -> None:
    items, containers, placements, relations = _fixture()
    rules = deepcopy(load_config(root / "config/level_06/nesting_rules.yaml"))
    checked = validate_compound_geometry(items, containers, placements, relations, rules, support_threshold=0.8, support_epsilon_mm=1e-4)

    assert checked.payload()["model"] == "compound_root_effective_envelope_geometry_v1"
    assert checked.projection is not None
