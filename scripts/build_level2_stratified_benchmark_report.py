"""Tạo report promotion V2 sau khi cả ba tầng benchmark đã hoàn thành."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from container_packing.benchmarks.stratified_evidence import (  # noqa: E402
    build_stratified_evidence,
    write_stratified_evidence,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--random-run-dir", type=Path, required=True)
    parser.add_argument("--stress-run-dir", type=Path, required=True)
    parser.add_argument("--prefix-run-dir", type=Path, required=True)
    parser.add_argument("--output-prefix", type=Path, required=True)
    args = parser.parse_args(argv)
    report = build_stratified_evidence({
        "random_distribution": args.random_run_dir,
        "stress": args.stress_run_dir,
        "prefix_regression": args.prefix_run_dir,
    })
    json_path, markdown_path = write_stratified_evidence(report, args.output_prefix)
    print(f"Functional gate : {report['functional_gate']['status']}")
    print(f"Provenance gate : {report['provenance_gate']['status']}")
    print(f"Decision        : {report['governance_decision']}")
    print(f"JSON   : {json_path}")
    print(f"Report : {markdown_path}")
    return 0 if report["promotion_to_canonical_allowed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
