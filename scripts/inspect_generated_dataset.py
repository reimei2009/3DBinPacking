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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = inspect_generated_dataset(DatasetInspectionRequest(
        manifest_path=args.manifest,
        level_id=args.level,
        mode=InspectionMode(args.mode),
        output_root=args.output_root,
        project_root=ROOT,
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
