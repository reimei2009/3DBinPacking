"""Download the complete checksum-pinned official MPV source bundle."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from container_packing.data.mpv_workflow import download_mpv_bundle  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Tai tron bo bundle MPV chinh thuc theo TOFU checksum lock; khong ghi de artifact khac.",
    )
    parser.add_argument("--lock", type=Path, default=Path("config/level_02/mpv_source_lock.yaml"))
    parser.add_argument("--destination-root", type=Path, default=Path("data/external/mpv_3dbpp"))
    args = parser.parse_args(argv)
    lock = args.lock if args.lock.is_absolute() else ROOT / args.lock
    destination = args.destination_root if args.destination_root.is_absolute() else ROOT / args.destination_root
    result = download_mpv_bundle(lock, destination_root=destination)
    print(f"MPV source bundle: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
