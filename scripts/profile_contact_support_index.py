"""Profile representative on/off contact-support index pairs."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from container_packing.benchmarks.profiling import run_contact_index_profile


_DEFAULT_GROUPS = {
    "level_04": ("contact_largest_volume_i500", "contact_payload_pressure_i500"),
    "level_05": ("contact_random101_i500", "contact_payload_pressure_i500"),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Profile representative Level 4/5 contact-index A/B cases",
    )
    parser.add_argument("--level", choices=tuple(_DEFAULT_GROUPS), required=True)
    parser.add_argument("--source-run-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    result = run_contact_index_profile(
        level_id=args.level,
        source_run_dir=args.source_run_dir,
        comparison_groups=_DEFAULT_GROUPS[args.level],
        project_root=ROOT,
    )
    print(f"Trạng thái profiling: {result.status}")
    print(f"Số bài variant: {result.selected_case_count}")
    print(f"Số lượt chẩn đoán: {result.execution_count}")
    print(f"Thư mục profiling: {result.run_dir}")
    return 0 if result.status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
