"""Build immutable Level 4-5 constructor-portfolio evidence."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from container_packing.benchmarks.constructor_portfolio_acceptance import (  # noqa: E402
    evaluate_constructor_portfolio_acceptance,
    write_constructor_portfolio_acceptance,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--portfolio-run", action="append", type=Path, required=True)
    parser.add_argument("--baseline-run", action="append", type=Path, required=True)
    parser.add_argument(
        "--output-prefix", type=Path,
        default=Path("docs/reports/manual/level_04_05_constructor_portfolio_20260820"),
    )
    args = parser.parse_args(argv)
    report = evaluate_constructor_portfolio_acceptance(
        args.portfolio_run, args.baseline_run,
    )
    json_path, markdown_path = write_constructor_portfolio_acceptance(
        report, args.output_prefix,
    )
    print(f"Decision: {report['status']}")
    print(f"JSON    : {json_path}")
    print(f"Report  : {markdown_path}")
    return 0 if report["status"] in {"PROMOTED", "NOT_PROMOTED"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
