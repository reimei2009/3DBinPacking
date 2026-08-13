"""Registry versioned cho cac protocol benchmark duoc cong bo.

Registry chi mo ta maturity va exposure. Corpus/suite YAML van la nguon su that
cho tung phep chay cu the.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


_KINDS = {"canonical", "academic", "research", "superseded"}
_RUN_MODES = {"ui_quick", "cli_manual", "read_only"}


@dataclass(frozen=True)
class BenchmarkCatalogEntry:
    benchmark_id: str
    level_id: str
    kind: str
    label_vi: str
    description_vi: str
    protocol_file: Path
    run_mode: str
    baseline_algorithm: str | None = None
    replacement_id: str | None = None


@dataclass(frozen=True)
class BenchmarkCatalog:
    schema_version: str
    entries: tuple[BenchmarkCatalogEntry, ...]
    source_path: Path

    def for_level(self, level_id: str) -> tuple[BenchmarkCatalogEntry, ...]:
        return tuple(entry for entry in self.entries if entry.level_id == level_id)

    def get(self, benchmark_id: str) -> BenchmarkCatalogEntry:
        matches = [entry for entry in self.entries if entry.benchmark_id == benchmark_id]
        if not matches:
            raise KeyError(f"Unknown benchmark catalog entry: {benchmark_id}")
        return matches[0]


def load_benchmark_catalog(
    path: str | Path, *, project_root: str | Path | None = None,
) -> BenchmarkCatalog:
    source_path = Path(path).resolve()
    root = (
        Path(project_root).resolve()
        if project_root is not None
        else source_path.parents[3]
    )
    try:
        payload = yaml.safe_load(source_path.read_text(encoding="utf-8-sig"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"Cannot read benchmark catalog {source_path}: {exc}") from exc
    if not isinstance(payload, dict) or str(payload.get("schema_version")) != "1.0":
        raise ValueError("Benchmark catalog must be a schema_version 1.0 mapping")
    raw_entries: Any = payload.get("benchmarks")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise ValueError("Benchmark catalog must contain a non-empty benchmarks list")

    entries: list[BenchmarkCatalogEntry] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_entries, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"benchmark catalog entry {index} must be a mapping")
        benchmark_id = str(raw.get("benchmark_id", "")).strip()
        if not benchmark_id or benchmark_id in seen:
            raise ValueError(f"benchmark_id is missing or duplicated: {benchmark_id!r}")
        seen.add(benchmark_id)
        kind = str(raw.get("kind", ""))
        run_mode = str(raw.get("run_mode", ""))
        if kind not in _KINDS:
            raise ValueError(f"Unsupported benchmark kind for {benchmark_id}: {kind}")
        if run_mode not in _RUN_MODES:
            raise ValueError(f"Unsupported benchmark run_mode for {benchmark_id}: {run_mode}")
        protocol_value = str(raw.get("protocol_file", "")).strip()
        protocol_file = Path(protocol_value)
        protocol_file = (
            protocol_file.resolve()
            if protocol_file.is_absolute()
            else (root / protocol_file).resolve()
        )
        if not protocol_file.is_file():
            raise ValueError(
                f"Benchmark protocol for {benchmark_id} does not exist: {protocol_file}"
            )
        entries.append(BenchmarkCatalogEntry(
            benchmark_id=benchmark_id,
            level_id=str(raw.get("level_id", "")).strip(),
            kind=kind,
            label_vi=str(raw.get("label_vi", benchmark_id)).strip(),
            description_vi=str(raw.get("description_vi", "")).strip(),
            protocol_file=protocol_file,
            run_mode=run_mode,
            baseline_algorithm=(
                str(raw["baseline_algorithm"]) if raw.get("baseline_algorithm") else None
            ),
            replacement_id=(
                str(raw["replacement_id"]) if raw.get("replacement_id") else None
            ),
        ))
    return BenchmarkCatalog("1.0", tuple(entries), source_path)
