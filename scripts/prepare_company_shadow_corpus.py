"""Materialize the governed company-like shadow population."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from container_packing.productization.company_corpus import (  # noqa: E402
    load_company_corpus_contract,
    prepare_company_shadow_corpus,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--contract",
        default="config/productization/company_like_shadow_v1.yaml",
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    contract = load_company_corpus_contract(args.contract, root=ROOT)
    result = prepare_company_shadow_corpus(contract, overwrite=args.overwrite)
    print(f"Corpus              : {result['corpus_id']}")
    print(f"Evidence class      : {result['evidence_class']}")
    print(f"Items / containers  : {result['item_count']} / {result['container_count']}")
    print("Production evidence : NO")
    print(f"Manifest            : {result['company_shadow_manifest']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
