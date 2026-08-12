"""Tạo evidence KPI/MES/repair Level 2 từ các benchmark run được chỉ định."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from container_packing.benchmarks.level2_kpi_acceptance import (  # noqa: E402
    build_level2_kpi_acceptance_report,
    write_level2_kpi_acceptance_report,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--control-run", type=Path, required=True)
    parser.add_argument("--kpi-run", type=Path, action="append", required=True)
    parser.add_argument("--repair-run", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("docs/reports/manual"))
    parser.add_argument("--report-id")
    args = parser.parse_args(argv)
    report_id = args.report_id or f"level_02_kpi_acceptance_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    report = build_level2_kpi_acceptance_report(
        control_run=args.control_run, kpi_runs=args.kpi_run, repair_run=args.repair_run,
    )
    json_path, markdown_path = write_level2_kpi_acceptance_report(report, args.output_dir / report_id)
    print(f"KPI promotion : {report['promotion']['kpi_promotion']}")
    print(f"MES comparator: {report['promotion']['mes_fast_comparator']}")
    print(f"Repair fallback: {report['promotion']['repair_fallback']}")
    print(f"JSON           : {json_path}")
    print(f"Report         : {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
