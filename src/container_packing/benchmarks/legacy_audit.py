"""Read-only audit for legacy Level 2 interactive benchmark outputs."""

from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from typing import Any

import pandas as pd


def _tree_size(path: Path) -> int:
    return sum(entry.stat().st_size for entry in path.rglob("*") if entry.is_file())


def _file_checksum(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_level2_default_source_benchmarks(root: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return candidate legacy benchmark dirs and their referenced source runs.

    This function never deletes, moves, or changes any run. A run is a candidate
    only when its persisted manifest proves it is an interactive Level 2 benchmark
    executed from ``config/level_02/default.yaml``.
    """
    project_root = Path(root).resolve()
    runs_root = project_root / "outputs" / "level_02" / "runs"
    benchmark_records: list[dict[str, Any]] = []
    referenced: dict[str, dict[str, Any]] = {}
    if not runs_root.is_dir():
        return pd.DataFrame(), pd.DataFrame()
    for manifest_path in sorted(runs_root.glob("*/manifest.json")):
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        config_file = str(manifest.get("config_file", "")).replace("\\", "/")
        if not (
            manifest.get("run_type") == "benchmark"
            and manifest.get("suite_id") == "level_02_interactive_comparison"
            and config_file.endswith("config/level_02/default.yaml")
        ):
            continue
        run_dir = manifest_path.parent
        record = {
            "benchmark_run_id": manifest.get("run_id", run_dir.name),
            "run_dir": str(run_dir),
            "status": manifest.get("status"),
            "created_at_utc": manifest.get("created_at_utc"),
            "config_file": manifest.get("config_file"),
            "size_bytes": _tree_size(run_dir),
            "source_run_count": len(manifest.get("source_runs", [])),
            "manifest_checksum": _file_checksum(manifest_path),
            "consumer": "historical_ui_only",
            "can_regenerate": True,
            "cleanup_reason": "interactive benchmark used the legacy default Level 2 source",
            "recommended_action": "review_then_delete",
        }
        benchmark_records.append(record)
        for raw_source in manifest.get("source_runs", []):
            source = Path(str(raw_source))
            if not source.is_absolute():
                source = project_root / source
            key = str(source.resolve())
            referenced.setdefault(key, {
                "source_run_dir": key,
                "exists": source.is_dir(),
                "size_bytes": _tree_size(source) if source.is_dir() else 0,
                "referenced_by_count": 0,
                "referenced_by_benchmark_ids": [],
                "manifest_checksum": _file_checksum(source / "manifest.json"),
                "can_regenerate": True,
                "cleanup_reason": "source run is referenced only by a legacy interactive benchmark",
                "recommended_action": "retain_until_reference_audit",
            })["referenced_by_count"] += 1
            referenced[key]["referenced_by_benchmark_ids"].append(
                str(manifest.get("run_id", run_dir.name))
            )
    benchmarks = pd.DataFrame(benchmark_records)
    sources = pd.DataFrame(referenced.values())
    return benchmarks, sources
