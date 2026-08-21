"""Publish versioned repair early-stop V1 research evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from container_packing.productization.repair_evidence import (  # noqa: E402
    evaluate_repair_early_stop_v1,
    render_repair_early_stop_v1_markdown,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument(
        "--output-prefix",
        default="docs/reports/manual/level_02_repair_early_stop_v1_20260821",
    )
    args = parser.parse_args(argv)
    report = evaluate_repair_early_stop_v1(args.run_dir)
    prefix = ROOT / args.output_prefix
    prefix.parent.mkdir(parents=True, exist_ok=True)
    prefix.with_suffix(".json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    prefix.with_suffix(".md").write_text(
        render_repair_early_stop_v1_markdown(report), encoding="utf-8",
    )
    print(f"Decision: {report['decision']}")
    print(f"Report  : {prefix.with_suffix('.md')}")
    return 0 if report["decision"] == "NOT_PROMOTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
