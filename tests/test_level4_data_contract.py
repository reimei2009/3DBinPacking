from __future__ import annotations

import csv
from pathlib import Path

from container_packing.data_loader import load_config


def test_level4_stackability_contract_matches_observed_raw_data(root: Path) -> None:
    contract = load_config(root / "config/level_04/stackability_rules.yaml")
    with (root / "data/raw/dataset_small_items_original.csv").open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert contract["level_id"] == "level_04"
    assert contract["compatibility"]["mode"] == "same_stackability_code"
    assert contract["compatibility"]["non_stackable_codes"] == []
    assert contract["stack_limit"]["semantics"] == "maximum_layers_in_parent_chain_including_root"
    assert {row["stackability_code"] for row in rows} == {"0", "1", "2", "3", "4", "5", "6"}
    assert {row["max_stackability"] for row in rows} == {"4", "100"}
    assert all(int(row["max_stackability"]) > 0 for row in rows)


def test_level4_contract_keeps_non_stackable_semantics_explicit(root: Path) -> None:
    contract = load_config(root / "config/level_04/stackability_rules.yaml")

    assert contract["relationships"]["require_unique_declared_parent"] is True
    assert contract["relationships"]["load_transfer_mode"] == "inactive"
    assert contract["stack_limit"]["source_status"] == "project_v1_convention_pending_field_definition"
