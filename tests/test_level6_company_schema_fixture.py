from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from container_packing.data_loader import load_config
from container_packing.levels.level_06_pipeline import run_from_config


@pytest.mark.parametrize(
    ("algorithm_id", "config_name"),
    [
        ("extreme_point_ffd_nesting_fixture", "company_schema_nesting_fixture.yaml"),
        ("extreme_point_best_fit_nesting_fixture", "company_schema_nesting_best_fit_fixture.yaml"),
    ],
)
def test_company_schema_mapping_flows_through_level6_runtime_and_output_contract(
    root: Path, tmp_path: Path, algorithm_id: str, config_name: str
) -> None:
    config = load_config(root / "config/level_06/experiments" / config_name)
    config["paths"]["processed_dir"] = str(tmp_path / "processed")
    config["paths"]["manifest_json"] = str(tmp_path / "processed/latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / "outputs")
    config_path = tmp_path / config_name
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    result = run_from_config(
        config_path, item_count=4, container_count=1, algorithm_id=algorithm_id
    )

    assert result.solve.status == "FEASIBLE"
    assert result.validation is not None and result.validation.valid
    assert result.metadata["nesting_relation_count"] == 2
    assert result.metadata["compound_count"] == 2
    assert result.metadata["load_transfer_edge_count"] == 1
    run_dir = Path(result.metadata["run_dir"])
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    snapshot = pd.read_csv(run_dir / "input_snapshot/items.csv")
    relations = pd.read_csv(run_dir / "solution/nesting_relations.csv")
    transfer = pd.read_csv(run_dir / "solution/load_transfer.csv")

    assert manifest["source_adapter"]["source_id"] == "synthetic_company_schema_level_06_v1"
    assert manifest["source_adapter"]["nesting_semantics"] == "incremental_height_of_item"
    assert {"customer_priority", "source_comment"} <= set(snapshot.columns)
    assert snapshot.loc[snapshot["id_item"] == "COMP-ROOT-01", "customer_priority"].item() == "high"
    assert relations[["host_item_id", "child_item_id"]].values.tolist() == [
        ["COMP-MID-01", "COMP-CHILD-01"],
        ["COMP-ROOT-01", "COMP-MID-01"],
    ]
    assert transfer[["supporter_item_id", "child_item_id"]].values.tolist() == [
        ["COMP-ROOT-01", "COMP-TOP-01"],
    ]
