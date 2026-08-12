"""Chuẩn hóa capture MPV đã xác minh thành input Level 2 cô lập."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from container_packing.data.mpv_corpus import normalize_mpv_capture  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Chuẩn hóa capture MPV có version. Lệnh này không tải, biên dịch "
            "hoặc chạy source chưa được xác minh."
        ),
    )
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--import-manifest", type=Path, required=True)
    parser.add_argument("--instance-id", required=True)
    parser.add_argument("--physical-container-count", type=int)
    parser.add_argument("--container-cost", type=float, default=1.0)
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path("data/interim/mpv_3dbpp/acceptance_primary"),
    )
    args = parser.parse_args(argv)
    if args.physical_container_count is not None and args.physical_container_count <= 0:
        parser.error("--physical-container-count phải là số dương")
    output_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    result = normalize_mpv_capture(
        args.capture,
        import_manifest_path=args.import_manifest,
        output_dir=output_dir,
        instance_id=args.instance_id,
        physical_container_count=args.physical_container_count,
        container_cost=args.container_cost,
    )
    print(f"Corpus ID       : {result.corpus_id}")
    print(f"Items           : {result.item_count}")
    print(f"Containers      : {result.container_count}")
    print(f"Output directory: {result.output_dir}")
    print(f"Manifest        : {result.manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
