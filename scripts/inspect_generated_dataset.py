"""Inspect generated synthetic datasets without invoking a packing solver."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from container_packing.dataset_inspection import (  # noqa: E402
    DatasetInspectionRequest,
    InspectionIntent,
    InspectionMode,
    inspect_generated_dataset,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate generation provenance/schema and measure CSV read performance. "
            "This command never invokes a solver."
        )
    )
    parser.add_argument("--manifest", required=True, type=Path, help="Path to generation_manifest.json")
    parser.add_argument("--level", default="level_08", help="Level-isolated output namespace")
    parser.add_argument(
        "--mode", choices=[value.value for value in InspectionMode], default=InspectionMode.STREAM.value,
        help="stream (bounded memory), materialize (pandas), or both",
    )
    parser.add_argument("--output-root", type=Path, default=Path("outputs"))
    parser.add_argument(
        "--intent",
        choices=[value.value for value in InspectionIntent],
        default=InspectionIntent.DATASET_INSPECTION.value,
        help="dataset_inspection only validates generated files; inventory_scale_gate also checks inventory normalization and lazy subset preview without invoking a solver",
    )
    parser.add_argument("--inventory-preview-items", type=int, default=20)
    parser.add_argument("--inventory-preview-candidates", type=int, default=32)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = inspect_generated_dataset(DatasetInspectionRequest(
        manifest_path=args.manifest,
        level_id=args.level,
        mode=InspectionMode(args.mode),
        output_root=args.output_root,
        project_root=ROOT,
        intent=InspectionIntent(args.intent),
        inventory_preview_item_count=args.inventory_preview_items,
        inventory_preview_candidates=args.inventory_preview_candidates,
    ))
    phases = [phase for phase in (result.provenance, result.stream, result.materialize) if phase is not None]
    print("\n=== GENERATED DATASET INSPECTION ===")
    print(f"Status        : {result.status}")
    print(f"Profile       : {result.profile_id}")
    print(f"Usage         : {result.usage_class} / {result.capacity_qualification}")
    for phase in phases:
        print(
            f"{phase.phase.title():<14}: {phase.status}; rows={phase.rows_processed}; "
            f"time={phase.runtime_seconds:.3f}s; peak RSS={phase.peak_rss_mb:.1f} MB; "
            f"delta RSS={phase.rss_delta_mb:.1f} MB"
        )
    print("Solver invoked: False")
    if result.inventory_scale_gate is not None:
        gate = result.inventory_scale_gate
        print(
            f"Inventory gate: {gate.status}; physical={gate.physical_container_count}; "
            f"types={gate.equivalent_type_count}; lower-bound={gate.lower_bound}; "
            f"candidates={gate.candidate_count}; time={gate.runtime_seconds:.3f}s; "
            f"peak RSS={gate.peak_rss_mb:.1f} MB"
        )
    print(f"Report        : {result.run_dir / 'reports' / 'dataset_inspection.json'}")
    if result.issues:
        print("Issues:")
        for issue in result.issues[:5]:
            print(f"  - [{issue.phase}/{issue.code}] {issue.message}")
        if len(result.issues) > 5:
            print(f"  - ... {len(result.issues) - 5} more issue(s) in report")
    return 0 if result.valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
