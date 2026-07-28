from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from container_packing.data_loader import load_config
from container_packing.levels.center_of_mass import CenterOfMassError, evaluate_center_of_mass
from container_packing.levels.level_07_validation import validate_container_balance
from container_packing.schemas import Container, Item, Placement


def _container() -> Container:
    return Container("C1", 1000.0, 1000.0, 1000.0, 1000.0, 100.0)


def _item(item_id: str, weight_kg: float) -> Item:
    return Item(item_id, 200.0, 200.0, 200.0, weight_kg)


def _placement(item_id: str, weight_kg: float, x_mm: float, y_mm: float) -> Placement:
    return Placement(item_id, "C1", x_mm, y_mm, 0.0, 200.0, 200.0, 200.0, weight_kg)


def _config(root: Path) -> dict:
    return load_config(root / "config/level_07/balance_rules.yaml")


def test_pure_engine_calculates_centered_mass_weighted_cog(root: Path) -> None:
    placements = [_placement("A", 10.0, 0.0, 400.0), _placement("B", 10.0, 800.0, 400.0)]

    evaluation = evaluate_center_of_mass(placements, [_container()], _config(root))

    assert len(evaluation.records) == 1
    record = evaluation.records[0]
    assert record.total_weight_kg == 20.0
    assert record.center_x_mm == 500.0
    assert record.center_y_mm == 500.0
    assert record.center_z_mm == 100.0
    assert record.longitudinal_ratio == 0.5
    assert record.lateral_ratio == 0.5
    assert record.balanced is True


def test_validator_accepts_centered_fixture_and_emits_independent_payload(root: Path) -> None:
    items = [_item("A", 10.0), _item("B", 10.0)]
    placements = [_placement("A", 10.0, 0.0, 400.0), _placement("B", 10.0, 800.0, 400.0)]

    result = validate_container_balance(items, [_container()], placements, _config(root))

    assert result.result.valid
    assert result.records[0].balanced
    assert result.payload()["model"] == "mass_weighted_item_geometric_center_v1"
    assert result.payload()["records"][0]["balance_profile_source"] == "synthetic_symmetric_center_band_v1"


def test_validator_rejects_longitudinal_and_lateral_imbalance(root: Path) -> None:
    items = [_item("A", 90.0), _item("B", 10.0)]
    placements = [_placement("A", 90.0, 0.0, 0.0), _placement("B", 10.0, 800.0, 800.0)]

    result = validate_container_balance(items, [_container()], placements, _config(root))

    assert result.result.valid is False
    assert {issue.code for issue in result.result.issues} == {
        "LONGITUDINAL_CENTER_OF_MASS_OUT_OF_BAND",
        "LATERAL_CENTER_OF_MASS_OUT_OF_BAND",
    }
    assert result.records[0].absolute_longitudinal_offset_ratio == pytest.approx(0.32)
    assert result.records[0].absolute_lateral_offset_ratio == pytest.approx(0.32)


def test_validator_rejects_weight_mismatch_without_using_solver_state(root: Path) -> None:
    result = validate_container_balance(
        [_item("A", 10.0)], [_container()], [_placement("A", 9.0, 400.0, 400.0)], _config(root)
    )

    assert result.result.valid is False
    assert result.records == ()
    assert result.result.issues[0].code == "BALANCE_WEIGHT_MISMATCH"


def test_pure_engine_rejects_invalid_placement_weight_and_unknown_container(root: Path) -> None:
    with pytest.raises(CenterOfMassError, match="positive weight_kg"):
        evaluate_center_of_mass([_placement("A", 0.0, 400.0, 400.0)], [_container()], _config(root))

    unknown = Placement("A", "UNKNOWN", 0.0, 0.0, 0.0, 200.0, 200.0, 200.0, 1.0)
    with pytest.raises(CenterOfMassError, match="unknown container"):
        evaluate_center_of_mass([unknown], [_container()], _config(root))


def test_validator_respects_explicit_container_tolerance_override(root: Path) -> None:
    config = deepcopy(_config(root))
    config["balance_profile"]["overrides"] = [{
        "container_id": "C1",
        "max_longitudinal_offset_ratio": 0.33,
        "max_lateral_offset_ratio": 0.33,
        "balance_profile_source": "fixture_override",
    }]
    items = [_item("A", 90.0), _item("B", 10.0)]
    placements = [_placement("A", 90.0, 0.0, 0.0), _placement("B", 10.0, 800.0, 800.0)]

    result = validate_container_balance(items, [_container()], placements, config)

    assert result.result.valid
    assert result.records[0].balance_profile_source == "fixture_override"
