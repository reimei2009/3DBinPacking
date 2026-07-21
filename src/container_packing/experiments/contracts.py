"""Stable extension contracts for levels and optimization algorithms."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Any


@dataclass(frozen=True)
class ExperimentRequest:
    level_id: str
    algorithm_id: str
    config_path: Path
    item_count: int
    container_count: int
    environment: str = "local"
    random_seed: int | None = None
    algorithm_parameters: dict[str, Any] | None = None


@dataclass(frozen=True)
class AlgorithmDefinition:
    algorithm_id: str
    family: str
    description: str
    supported_levels: tuple[str, ...]
    local_friendly: bool
    gpu_recommended: bool = False


@dataclass(frozen=True)
class LevelDefinition:
    level_id: str
    description: str
    default_config: Path
    supported_algorithms: tuple[str, ...]
    run: Callable[[ExperimentRequest], Any]
    prepare: Callable[[ExperimentRequest], dict[str, Any]]
    validate_run: Callable[[Path], Any]
