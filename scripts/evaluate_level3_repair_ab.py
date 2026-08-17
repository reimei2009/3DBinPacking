"""Evaluate the bounded Level 3 repair A/B artifact."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from container_packing.benchmarks import write_level3_repair_acceptance  # noqa: E402


def _configure_utf8_console() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _configure_utf8_console()
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument(
        "--publish-prefix", type=Path,
        help="Optional report path without .json/.md suffix",
    )
    parser.add_argument(
        "--dirty-evidence-note",
        help="Required provenance explanation when publishing a git-dirty run",
    )
    args = parser.parse_args(argv)
    report = write_level3_repair_acceptance(
        args.run_dir,
        publish_prefix=args.publish_prefix,
        dirty_evidence_note=args.dirty_evidence_note,
    )
    print(f"Trạng thái: {report['status']}")
    print(f"Lượt chạy: {report['execution_count']}/72")
    print(f"So sánh ghép cặp: {report['comparison_count']}/18")
    print(f"Nhóm deterministic: {report['deterministic_group_count']}/36")
    if report["errors"]:
        print("Lỗi gate:")
        for value in report["errors"]:
            print(f"- {value}")
    return 0 if report["repair_ui_qualified"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
