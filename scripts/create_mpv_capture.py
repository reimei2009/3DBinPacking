"""Chuyển raw instance MPV đã khóa checksum sang capture JSON có version."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from container_packing.data.mpv_corpus import (  # noqa: E402
    create_mpv_capture_from_native_instances,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Tạo capture JSON từ các file native do MPV generator đã xác minh sinh ra.",
    )
    parser.add_argument("--execution-manifest", type=Path, required=True)
    parser.add_argument("--import-manifest", type=Path, required=True)
    parser.add_argument("--instance", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    result = create_mpv_capture_from_native_instances(
        args.instance,
        execution_manifest_path=args.execution_manifest,
        import_manifest_path=args.import_manifest,
        output_path=args.output,
    )
    print(f"Capture: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
