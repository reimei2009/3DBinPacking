"""Tạo view Level 2 tối đa 20.000 kiện/5.000 container từ corpus 100k bất biến."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from container_packing.solver_research_subset import (  # noqa: E402
    MAXIMUM_SOLVER_RESEARCH_ITEMS,
    SolverResearchSubsetRequest,
    materialize_solver_research_subset,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-manifest",
        type=Path,
        default=Path("data/interim/synthetic/empirical_scale_100k_5k_v1/generation_manifest.json"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/interim/synthetic/level_02_solver_research_i20000_f5000_v1"),
    )
    parser.add_argument("--items", type=int, default=MAXIMUM_SOLVER_RESEARCH_ITEMS)
    args = parser.parse_args(argv)
    result = materialize_solver_research_subset(SolverResearchSubsetRequest(
        source_manifest=(ROOT / args.source_manifest).resolve(),
        output_dir=(ROOT / args.output_dir).resolve(),
        item_count=args.items,
    ))
    print("\n=== LEVEL 2 SOLVER-RESEARCH VIEW ===")
    print(f"Profile              : {result.profile_id}")
    print(f"Items / containers   : {result.item_count} / {result.container_count}")
    print(f"Volume margin        : {result.volume_margin_ratio:.3f}")
    print(f"Payload margin       : {result.payload_margin_ratio:.3f}")
    print("Solver acceptance    : ALLOWED (dataset qualification)")
    print("Web exposure         : DISABLED until the manual runtime gate passes")
    print(f"Manifest             : {result.manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
