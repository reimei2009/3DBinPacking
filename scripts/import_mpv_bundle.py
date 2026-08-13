"""Nhập bundle MPV local sau khi kiểm tra toàn bộ SHA-256."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from container_packing.data.mpv_corpus import import_mpv_bundle  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Nhập đầy đủ bundle MPV local với checksum đã pin.",
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--destination-root", type=Path,
        default=Path("data/external/mpv_3dbpp"),
    )
    args = parser.parse_args(argv)
    destination = (
        args.destination_root if args.destination_root.is_absolute()
        else ROOT / args.destination_root
    )
    result = import_mpv_bundle(args.manifest, destination_root=destination)
    print(f"Bundle ID       : {result.bundle_id}")
    print(f"Bundle checksum : {result.bundle_checksum}")
    print(f"Import manifest : {result.import_manifest_path}")
    print("Artifacts       : " + ", ".join(value.role for value in result.artifacts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
