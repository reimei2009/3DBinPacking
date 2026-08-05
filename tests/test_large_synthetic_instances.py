from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest
import yaml

from container_packing.provenance import sha256_file
from container_packing.source_adapter import load_csv_source
from container_packing.synthetic_instances import (
    generate_large_synthetic_instances,
    load_large_synthetic_profile,
)


def _small_profile(root: Path, output: Path):
    profile = load_large_synthetic_profile("config/synthetic/scale_1k_100.yaml", root=root)
    return replace(
        profile,
        item_count=50,
        delivery_stop_count=5,
        container_quantities={"C1": 0, "C2": 0, "C3": 0, "C4": 0, "C5": 5},
        output_dir=output,
    )


def test_empirical_generator_preserves_source_and_is_deterministic(root: Path, tmp_path: Path) -> None:
    raw_path = root / "data/raw/dataset_small_items_original.csv"
    before = sha256_file(raw_path)
    first = generate_large_synthetic_instances(_small_profile(root, tmp_path / "one"))
    second = generate_large_synthetic_instances(_small_profile(root, tmp_path / "two"))

    assert before == sha256_file(raw_path)
    assert first["item_count"] == 50
    assert first["container_count"] == 5
    assert first["capacity_status"] == "capacity_feasible"
    assert first["capacity_qualification"] == "solver_qualified"
    assert first["solver_acceptance_allowed"] is True
    assert first["file_sha256"] == second["file_sha256"]
    assert first["profile_fingerprint"] == second["profile_fingerprint"]


def test_different_seed_changes_sampled_physical_population(root: Path, tmp_path: Path) -> None:
    base = _small_profile(root, tmp_path / "seed-one")
    first = generate_large_synthetic_instances(base)
    second = generate_large_synthetic_instances(replace(base, seed=base.seed + 1, output_dir=tmp_path / "seed-two"))

    assert first["file_sha256"]["solver_items"] != second["file_sha256"]["solver_items"]


def test_catalog_frequency_instances_and_delivery_enrichment_are_complete(root: Path, tmp_path: Path) -> None:
    result = generate_large_synthetic_instances(_small_profile(root, tmp_path / "generated"))
    output = Path(result["manifest_path"]).parent
    templates = pd.read_csv(output / "item_template_catalog.csv")
    instances = pd.read_csv(output / "item_instances.csv")
    delivery = pd.read_csv(output / "delivery_enrichment.csv")
    solver_items = pd.read_csv(output / "solver_items.csv")

    assert templates["source_row_count"].sum() == 501
    assert len(instances) == len(delivery) == len(solver_items) == 50
    assert instances["item_id"].is_unique
    assert set(instances["item_template_id"]) <= set(templates["item_template_id"])
    assert set(delivery["delivery_priority"]) == {1, 2, 3, 4, 5}
    assert set(instances["item_id"]) == set(delivery["item_id"]) == set(solver_items["id_item"])


def test_physical_containers_of_one_type_are_identical_except_identity(root: Path, tmp_path: Path) -> None:
    result = generate_large_synthetic_instances(_small_profile(root, tmp_path / "generated"))
    containers = pd.read_csv(Path(result["solver_containers_path"]))
    comparable = containers.drop(columns=["container_id"])

    assert len(containers) == 5
    assert containers["container_id"].is_unique
    assert set(containers["container_type_id"]) == {"C5"}
    assert len(comparable.drop_duplicates()) == 1
    source_c5 = pd.read_csv(root / "data/raw/level_08/cross_level/container_catalog_c1_c10_v1.csv").query(
        "container_id == 'C5'"
    ).iloc[0]
    for field in ("length_mm", "width_mm", "height_mm", "max_weight_kg", "cost", "volume_m3"):
        assert containers.iloc[0][field] == source_c5[field]


def test_solver_ready_items_are_accepted_by_level8_source_adapter(root: Path, tmp_path: Path) -> None:
    result = generate_large_synthetic_instances(_small_profile(root, tmp_path / "generated"))
    adapted = load_csv_source(
        result["solver_items_path"],
        root / "config/common/data_sources/empirical_template_level_08.yaml",
    )

    assert len(adapted.frame) == 50
    assert adapted.delivery_semantics == "priority_and_stop"
    assert adapted.delivery_data_source == "empirical_template_level_08_enrichment_v1"
    assert "item_template_id" in adapted.preserved_extra_columns


def test_insufficient_capacity_is_rejected_without_publishing_partial_outputs(root: Path, tmp_path: Path) -> None:
    profile = replace(
        _small_profile(root, tmp_path / "insufficient"),
        item_count=200,
        container_quantities={"C1": 1, "C2": 0, "C3": 0, "C4": 0, "C5": 0},
    )
    with pytest.raises(ValueError, match="exceeds aggregate fleet capacity"):
        generate_large_synthetic_instances(profile)
    assert not (profile.output_dir / "generation_manifest.json").exists()
    assert not list(profile.output_dir.glob("*.tmp"))


def test_solver_research_rejects_aggregate_feasible_population_below_declared_margin(
    root: Path, tmp_path: Path,
) -> None:
    profile = replace(
        _small_profile(root, tmp_path / "below-policy"),
        minimum_volume_margin_ratio=10.0,
        minimum_payload_margin_ratio=10.0,
    )
    with pytest.raises(ValueError, match="does not meet the declared capacity policy"):
        generate_large_synthetic_instances(profile)
    assert not (profile.output_dir / "generation_manifest.json").exists()
    assert not list(profile.output_dir.glob("*.tmp"))


def test_data_pipeline_population_is_never_solver_acceptance_evidence(root: Path, tmp_path: Path) -> None:
    profile = replace(
        _small_profile(root, tmp_path / "pipeline"),
        usage_class="data_pipeline_only",
        minimum_volume_margin_ratio=1.0,
        minimum_payload_margin_ratio=1.0,
    )
    result = generate_large_synthetic_instances(profile)

    assert result["capacity_qualification"] == "pipeline_qualified"
    assert result["solver_acceptance_allowed"] is False
    assert result["recommended_use"] == "data_pipeline_testing_only"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("usage_class", "production", "usage_class must be"),
        ("minimum_volume_margin_ratio", 0.99, "must be at least 1.0"),
        ("reject_below_minimum", "yes", "must be boolean"),
    ],
)
def test_profile_rejects_invalid_capacity_policy(
    root: Path, tmp_path: Path, field: str, value: object, message: str,
) -> None:
    config = yaml.safe_load((root / "config/synthetic/base_large_instances.yaml").read_text(encoding="utf-8"))
    config["profile_id"] = "invalid"
    config["container_fleet"]["quantities"] = {"C5": 1}
    config["output"]["directory"] = str(tmp_path / "invalid")
    if field == "usage_class":
        config[field] = value
    else:
        config["capacity_policy"][field] = value
    path = tmp_path / "invalid.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_large_synthetic_profile(path, root=root)


def test_generation_refuses_implicit_overwrite(root: Path, tmp_path: Path) -> None:
    profile = _small_profile(root, tmp_path / "generated")
    generate_large_synthetic_instances(profile)
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        generate_large_synthetic_instances(profile)


def test_large_profiles_parse_without_generating_them(root: Path) -> None:
    expected = {
        "scale_1k_100.yaml": (1_000, 100),
        "scale_10k_500.yaml": (10_000, 500),
        "scale_10k_700.yaml": (10_000, 700),
        "scale_100k_5k.yaml": (100_000, 5_000),
        "scale_100k_7k.yaml": (100_000, 7_000),
        "stress_1m_50k.yaml": (1_000_000, 50_000),
        "scale_1m_70k.yaml": (1_000_000, 70_000),
    }
    for file_name, counts in expected.items():
        profile = load_large_synthetic_profile(root / "config/synthetic" / file_name, root=root)
        assert (profile.item_count, profile.container_count) == counts
