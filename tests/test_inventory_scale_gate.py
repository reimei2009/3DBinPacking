from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from container_packing.dataset_inspection import (
    DatasetInspectionRequest,
    InspectionIntent,
    InspectionMode,
    inspect_generated_dataset,
)
from container_packing.synthetic_instances import (
    generate_large_synthetic_instances,
    load_large_synthetic_profile,
)


def test_scale_gate_profiles_declare_expected_physical_and_type_counts(root: Path) -> None:
    fleet_500 = load_large_synthetic_profile(
        root / "config/synthetic/fleet_500_t10.yaml", root=root,
    )
    fleet_5000 = load_large_synthetic_profile(
        root / "config/synthetic/fleet_5000_t25.yaml", root=root,
    )

    assert (fleet_500.container_count, len(fleet_500.generated_container_type_ids)) == (500, 10)
    assert (fleet_5000.container_count, len(fleet_5000.generated_container_type_ids)) == (5_000, 25)
    assert sum(fleet_5000.generated_container_quantities.values()) == 5_000
    assert set(fleet_5000.generated_container_quantities.values()) == {200}


def test_inventory_scale_gate_normalizes_variants_and_previews_lazy_subsets(
    root: Path, tmp_path: Path,
) -> None:
    profile = load_large_synthetic_profile(
        root / "config/synthetic/fleet_5000_t25.yaml", root=root,
    )
    generated = generate_large_synthetic_instances(replace(
        profile,
        item_count=20,
        delivery_stop_count=5,
        container_quantities={f"C{index}": 10 for index in range(1, 6)},
        output_dir=tmp_path / "generated",
    ))

    result = inspect_generated_dataset(DatasetInspectionRequest(
        manifest_path=Path(generated["manifest_path"]),
        level_id="level_01",
        mode=InspectionMode.STREAM,
        intent=InspectionIntent.INVENTORY_SCALE_GATE,
        inventory_preview_item_count=10,
        inventory_preview_candidates=8,
        output_root=tmp_path / "outputs",
        project_root=root,
    ))

    assert result.valid
    assert result.inventory_scale_gate is not None
    evidence = result.inventory_scale_gate
    assert evidence.physical_container_count == 50
    assert evidence.equivalent_type_count == 25
    assert evidence.hard_precheck_valid
    assert 1 <= evidence.candidate_count <= 8
    assert len(set(evidence.candidate_signatures)) == evidence.candidate_count
    assert (result.run_dir / "reports/inventory_scale_gate.json").is_file()
