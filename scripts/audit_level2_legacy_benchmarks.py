"""Create a read-only, reviewable manifest for old Level 2 UI benchmarks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from container_packing.benchmarks.legacy_audit import audit_level2_default_source_benchmarks  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report-dir", type=Path, required=True,
        help="Empty or new directory for JSON/CSV review artifacts; no run is deleted.",
    )
    args = parser.parse_args(argv)
    report_dir = args.report_dir.resolve()
    if report_dir.exists() and any(report_dir.iterdir()):
        raise ValueError(f"Report directory must be empty: {report_dir}")
    report_dir.mkdir(parents=True, exist_ok=True)
    benchmarks, sources = audit_level2_default_source_benchmarks(ROOT)
    benchmarks.to_csv(report_dir / "legacy_benchmark_candidates.csv", index=False, encoding="utf-8")
    sources.to_csv(report_dir / "referenced_source_run_candidates.csv", index=False, encoding="utf-8")
    payload = {
        "mode": "dry_run",
        "action": "none",
        "benchmark_candidate_count": len(benchmarks),
        "source_run_candidate_count": len(sources),
        "benchmark_total_size_bytes": int(benchmarks.get("size_bytes", []).sum()) if not benchmarks.empty else 0,
        "source_total_size_bytes": int(sources.get("size_bytes", []).sum()) if not sources.empty else 0,
        "deletion_performed": False,
        "approval_required_before_deletion": True,
        "files": ["legacy_benchmark_candidates.csv", "referenced_source_run_candidates.csv"],
    }
    (report_dir / "audit_manifest.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8",
    )
    print(json.dumps(payload, indent=2))
    print(f"Review directory: {report_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
