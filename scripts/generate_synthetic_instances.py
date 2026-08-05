"""Generate reproducible large physical item/container populations."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from container_packing.synthetic_instances import (  # noqa: E402
    generate_large_synthetic_instances,
    load_large_synthetic_profile,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True, help="Schema-v2 YAML generation profile")
    parser.add_argument("--overwrite", action="store_true", help="Replace the exact profile output atomically")
    args = parser.parse_args()
    profile = load_large_synthetic_profile(args.profile, root=ROOT)
    result = generate_large_synthetic_instances(profile, overwrite=args.overwrite)
    capacity = result["capacity"]
    print(f"Profile              : {result['profile_id']}")
    print(f"Usage class          : {result['usage_class']}")
    print(f"Items / containers   : {result['item_count']} / {result['container_count']}")
    print(
        f"Volume margin        : {capacity['volume_margin_ratio']:.3f} / required "
        f"{result['capacity_policy']['minimum_volume_margin_ratio']:.3f}"
    )
    print(
        f"Payload margin       : {capacity['payload_margin_ratio']:.3f} / required "
        f"{result['capacity_policy']['minimum_payload_margin_ratio']:.3f}"
    )
    print(f"Qualification        : {result['capacity_qualification'].upper()}")
    print(f"Solver acceptance    : {'ALLOWED' if result['solver_acceptance_allowed'] else 'NOT ALLOWED'}")
    if result["usage_class"] == "data_pipeline_only":
        print("WARNING: This dataset is for data-pipeline testing only, not solver acceptance evidence.")
    print(f"Manifest             : {result['manifest_path']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
