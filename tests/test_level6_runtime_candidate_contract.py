from __future__ import annotations

from pathlib import Path

import yaml
import pandas as pd

from container_packing.data_loader import load_config
from container_packing.cli import terminal_preview
from container_packing.levels.level_06_candidate_contract import load_runtime_candidate_contract
from container_packing.levels.level_06_ffd_adapter import solve_nesting_aware_ffd_fixture
from container_packing.levels.level_06_pipeline import run_from_config
from container_packing.levels.registry import list_levels
from container_packing.schemas import Container, Item


def _fixture() -> tuple[list[Item], list[Container]]:
    return [
        Item("HOST", 100, 90, 80, 10, source={
            "stackability_code": "A", "max_stackability": "3",
            "nesting_group_id": "G1", "nesting_role": "host",
            "inner_length_mm": "110", "inner_width_mm": "100", "inner_height_mm": "90",
            "max_nesting_depth": "1", "nesting_data_source": "fixture_v1",
        }),
        Item("CHILD", 100, 90, 70, 10, source={
            "stackability_code": "A", "max_stackability": "3",
            "nesting_group_id": "G1", "nesting_role": "child",
            "nesting_increment_height_mm": "20", "nesting_data_source": "fixture_v1",
        }),
    ], [Container("C1", 200, 100, 250, 500, 1, volume_m3=0.005)]


def _signature(result) -> tuple[tuple[object, ...], ...]:
    return tuple(
        (value.item_id, value.container_id, value.x_mm, value.y_mm, value.z_mm,
         value.length_mm, value.width_mm, value.height_mm)
        for value in result.placements
    )


def test_runtime_candidate_contract_is_frozen_before_experimental_registration(root: Path) -> None:
    config = load_config(root / "config/level_06/runtime_candidate.yaml")

    contract = load_runtime_candidate_contract(config)

    assert contract.algorithm_id == "extreme_point_ffd_nesting_fixture"
    assert contract.fixture_id == "declared_chain_host_child_v1"
    assert contract.deterministic_repeats == 2
    level = next(level for level in list_levels() if level.level_id == "level_06")
    assert level.supported_algorithms == (
        "extreme_point_ffd_nesting_fixture",
        "extreme_point_best_fit_nesting_fixture",
    )


def test_frozen_acceptance_fixture_is_valid_and_deterministic(root: Path) -> None:
    config = load_config(root / "config/level_06/runtime_candidate.yaml")
    load_runtime_candidate_contract(config)
    items, containers = _fixture()

    first = solve_nesting_aware_ffd_fixture(items, containers, config)
    second = solve_nesting_aware_ffd_fixture(items, containers, config)

    for result in (first, second):
        assert result.outcome.solve.status == "FEASIBLE"
        assert result.validation is not None and result.validation.result.valid
        assert result.projection is not None and len(result.projection.compounds) == 1
        assert len(result.relations) == 1
    assert _signature(first) == _signature(second)


def test_experimental_runtime_uses_registry_pipeline_and_isolates_outputs(root: Path, tmp_path: Path) -> None:
    config = load_config(root / "config/level_06/experimental.yaml")
    config["paths"]["raw_items_csv"] = str(root / "data/raw/dataset_small_items_original.csv")
    config["paths"]["processed_dir"] = str(tmp_path / "processed/level_06")
    config["paths"]["manifest_json"] = str(tmp_path / "processed/level_06/latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / "outputs")
    config_path = tmp_path / "level_06_experimental.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    result = run_from_config(
        config_path, item_count=2, container_count=2,
        algorithm_id="extreme_point_ffd_nesting_fixture",
    )

    assert result.solve.status == "FEASIBLE"
    assert result.validation is not None and result.validation.valid
    assert result.metadata["n_items"] == 2
    assert result.metadata["experimental_runtime"] is True
    assert result.metadata["support_threshold"] == 0.8
    assert result.metadata["minimum_exact_support_ratio"] == 1.0
    assert result.metadata["all_centers_supported"] is True
    preview = terminal_preview(result, placement_limit=0)
    assert "Support threshold: 0.8" in preview
    assert "Nesting relations: 0 (no compatible declared relation in selected input)" in preview
    run_dir = (root / Path(result.metadata["run_dir"])).resolve()
    assert run_dir.is_relative_to(tmp_path / "outputs/level_06/runs")
    assert (run_dir / "solution" / "nesting_compounds.csv").is_file()


def test_declared_nesting_fixture_creates_one_relation_and_one_compound(root: Path, tmp_path: Path) -> None:
    config = load_config(root / "config/level_06/experiments/declared_nesting_fixture.yaml")
    config["paths"]["processed_dir"] = str(tmp_path / "processed/level_06")
    config["paths"]["manifest_json"] = str(tmp_path / "processed/level_06/latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / "outputs")
    config_path = tmp_path / "declared_nesting_fixture.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    result = run_from_config(
        config_path, item_count=2, container_count=1,
        algorithm_id="extreme_point_ffd_nesting_fixture",
    )

    assert result.solve.status == "FEASIBLE"
    assert result.validation is not None and result.validation.valid
    assert result.metadata["nesting_relation_count"] == 1
    assert result.metadata["compound_count"] == 1
    assert result.metadata["n_items"] == 2
    run_dir = (root / Path(result.metadata["run_dir"])).resolve()
    relations = pd.read_csv(run_dir / "solution" / "nesting_relations.csv")
    compounds = pd.read_csv(run_dir / "solution" / "nesting_compounds.csv")
    assert relations[["host_item_id", "child_item_id"]].values.tolist() == [["HOST-001", "CHILD-001"]]
    assert compounds.loc[0, "effective_height_mm"] == 120
