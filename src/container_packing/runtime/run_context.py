"""Unique, level-isolated run directory creation."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Sequence


def make_run_id(level_id: str, algorithm_id: str, item_count: int, container_count: int, seed: int) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{timestamp}__{level_id}__{algorithm_id}__i{item_count}_c{container_count}__seed{seed}"


def create_run_directory(
    root: Path, level_id: str, algorithm_id: str, item_count: int, container_count: int, seed: int,
) -> tuple[str, Path]:
    run_id = make_run_id(level_id, algorithm_id, item_count, container_count, seed)
    run_dir = root / level_id / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_id, run_dir


def create_benchmark_directory(root: Path, level_id: str, seeds: Sequence[int]) -> tuple[str, Path]:
    if not seeds:
        raise ValueError("Benchmark seeds must not be empty")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    if len(seeds) == 1:
        seed_label = f"seed{seeds[0]}"
    else:
        fingerprint = sha256(",".join(str(value) for value in seeds).encode("ascii")).hexdigest()[:8]
        seed_label = f"seeds{len(seeds)}_{fingerprint}"
    run_id = f"{timestamp}__{level_id}__benchmark__{seed_label}"
    run_dir = root / level_id / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_id, run_dir


def create_benchmark_corpus_directory(
    root: Path, level_id: str, corpus_id: str, seeds: Sequence[int],
) -> tuple[str, Path]:
    if not seeds:
        raise ValueError("Benchmark-corpus seeds must not be empty")
    safe_corpus_id = "".join(
        value if value.isalnum() or value in {"-", "_"} else "-" for value in corpus_id
    ).strip("-_")
    if not safe_corpus_id:
        raise ValueError("corpus_id must contain at least one letter or number")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    fingerprint = sha256(",".join(str(value) for value in seeds).encode("ascii")).hexdigest()[:8]
    seed_label = f"seed{seeds[0]}" if len(seeds) == 1 else f"seeds{len(seeds)}_{fingerprint}"
    run_id = f"{timestamp}__{level_id}__benchmark_corpus__{safe_corpus_id}__{seed_label}"
    run_dir = root / level_id / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_id, run_dir


def create_parameter_sweep_directory(
    root: Path, level_id: str, algorithm_id: str, seeds: Sequence[int],
) -> tuple[str, Path]:
    if not seeds:
        raise ValueError("Parameter-sweep seeds must not be empty")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    fingerprint = sha256(",".join(str(value) for value in seeds).encode("ascii")).hexdigest()[:8]
    seed_label = f"seed{seeds[0]}" if len(seeds) == 1 else f"seeds{len(seeds)}_{fingerprint}"
    run_id = f"{timestamp}__{level_id}__parameter_sweep__{algorithm_id}__{seed_label}"
    run_dir = root / level_id / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_id, run_dir
