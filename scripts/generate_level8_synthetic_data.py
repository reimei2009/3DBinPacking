"""Generate reproducible Level 8 synthetic delivery inputs; no solver is run."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from container_packing.synthetic_delivery import generate_synthetic_delivery_data, load_synthetic_delivery_profile  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, help="YAML profile relative to the repository root")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing generated profile explicitly")
    args = parser.parse_args(argv)
    profile = load_synthetic_delivery_profile(args.profile, root=ROOT)
    result = generate_synthetic_delivery_data(profile, overwrite=args.overwrite)
    print(f"Generated Level 8 profile: {result['profile_id']}")
    print(f"Items     : {result['item_count']} -> {result['item_path']}")
    print(f"Containers: {result['container_count']} -> {result['container_path']}")
    print(f"Manifest  : {result['manifest_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
