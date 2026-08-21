"""Evaluate one company-like shadow benchmark against declared candidate SLOs."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from container_packing.productization.company_corpus import load_company_corpus_contract  # noqa: E402
from container_packing.productization.slo import (  # noqa: E402
    publish_shadow_slo_evaluation,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--ui-evidence-run-dir", required=True)
    parser.add_argument(
        "--contract", default="config/productization/company_like_shadow_v1.yaml",
    )
    args = parser.parse_args()
    contract = load_company_corpus_contract(args.contract, root=ROOT)
    output, report = publish_shadow_slo_evaluation(
        args.run_dir,
        args.ui_evidence_run_dir,
        contract,
        root=ROOT,
    )
    print(f"Shadow SLO status: {report['status']}")
    print(f"Evaluation run   : {output}")
    return 0 if report["status"] == "SHADOW_PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
