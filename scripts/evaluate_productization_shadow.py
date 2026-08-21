"""Evaluate one company-like shadow benchmark against declared candidate SLOs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from container_packing.productization.company_corpus import load_company_corpus_contract  # noqa: E402
from container_packing.productization.slo import (  # noqa: E402
    evaluate_shadow_slo,
    render_shadow_slo_markdown,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument(
        "--contract", default="config/productization/company_like_shadow_v1.yaml",
    )
    parser.add_argument("--ui-response-p95-seconds", type=float)
    args = parser.parse_args()
    contract = load_company_corpus_contract(args.contract, root=ROOT)
    report = evaluate_shadow_slo(
        args.run_dir,
        contract,
        ui_response_p95_seconds=args.ui_response_p95_seconds,
    )
    output = Path(args.run_dir) / "benchmark"
    output.mkdir(parents=True, exist_ok=True)
    (output / "production_shadow_slo.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    (output / "production_shadow_slo.md").write_text(
        render_shadow_slo_markdown(report), encoding="utf-8",
    )
    print(f"Shadow SLO status: {report['status']}")
    print(f"Report directory : {output}")
    return 0 if report["status"] == "SHADOW_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
