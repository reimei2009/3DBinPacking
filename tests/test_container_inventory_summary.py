from pathlib import Path

from container_packing.application.service import get_container_inventory_summary
from container_packing.algorithms.search.inventory import normalize_container_inventory
from container_packing.reporting import container_summary
from container_packing.schemas import Container


def test_default_container_inventory_summary_is_read_only_and_grouped(root: Path) -> None:
    summary = get_container_inventory_summary(
        "config/level_01/default.yaml", root=root
    )

    assert summary.ready
    assert summary.physical_container_count == 5
    assert summary.available_container_count == 5
    assert summary.equivalent_type_count == 5
    assert len(summary.type_rows) == 5
    assert summary.inventory_fingerprint is not None
    assert len(summary.inventory_fingerprint) == 64
    assert all("display_type_id" in row for row in summary.type_rows)
    assert summary.total_available_volume_m3 > 0
    assert summary.total_available_payload_kg > 0


def test_missing_generated_catalog_is_reported_without_fallback(
    root: Path, tmp_path: Path,
) -> None:
    config = tmp_path / "missing_catalog.yaml"
    config.write_text(
        """
project:
  level_id: level_01
paths:
  raw_containers_csv: data/interim/not-present/containers.csv
containers: []
""".strip(),
        encoding="utf-8",
    )

    summary = get_container_inventory_summary(config, root=root)

    assert not summary.ready
    assert summary.physical_container_count == 0
    assert summary.error is not None


def test_inventory_keeps_source_type_label_but_groups_by_canonical_equivalence() -> None:
    containers = [
        Container("C1", 100, 100, 100, 1000, 50, volume_m3=0.001, source={"container_type_id": "BOX-A"}),
        Container("C2", 100, 100, 100, 1000, 50, volume_m3=0.001, source={"container_type_id": "BOX-A"}),
    ]

    inventory = normalize_container_inventory(containers)

    assert inventory.equivalent_type_count == 1
    assert inventory.groups[0].display_type_id == "BOX-A"
    assert inventory.groups[0].declared_type_ids == ("BOX-A",)
    assert inventory.inventory_fingerprint == normalize_container_inventory(containers).inventory_fingerprint
    summary = container_summary([], containers)
    assert list(summary["container_type_id"]) == ["BOX-A", "BOX-A"]
