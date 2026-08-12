"""Chạy executable MPV đã pin trong working directory tạm thời."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from container_packing.data.mpv_corpus import run_verified_mpv_generator  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Chạy MPV generator đã xác minh, không dùng shell và không ghi đè output.",
    )
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--output-root", type=Path,
        default=Path("data/interim/mpv_3dbpp/raw_generator_runs"),
    )
    args = parser.parse_args(argv)
    output = args.output_root if args.output_root.is_absolute() else ROOT / args.output_root
    result = run_verified_mpv_generator(args.config, output_root=output)
    print(f"Execution ID : {result.execution_id}")
    print(f"Output       : {result.output_dir}")
    print(f"Manifest     : {result.execution_manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
