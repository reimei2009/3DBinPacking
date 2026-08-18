"""Publish immutable Level 4-5 Contact/Support Index V2 evidence."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from container_packing.benchmarks import write_contact_index_acceptance  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--level4-run-dir", required=True, type=Path)
    parser.add_argument("--level5-run-dir", required=True, type=Path)
    parser.add_argument("--publish-prefix", required=True, type=Path)
    args = parser.parse_args(argv)
    report = write_contact_index_acceptance(
        args.level4_run_dir,
        args.level5_run_dir,
        publish_prefix=args.publish_prefix,
    )
    print(f"Trạng thái: {report['status']}")
    for level in ("level_04", "level_05"):
        value = report["levels"][level]
        print(
            f"{level}: {value['valid_execution_count']}/{value['execution_count']} VALID; "
            f"{value['deterministic_group_count']}/36 deterministic"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
