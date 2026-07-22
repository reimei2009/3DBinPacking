"""Named, validated benchmark suites for fair algorithm comparison."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class BenchmarkScenario:
    """One fixed Level-specific input condition shared by every algorithm."""

    scenario_id: str
    description: str
    item_count: int
    container_count: int
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class BenchmarkSuite:
    """A reproducible comparison protocol loaded from YAML."""

    suite_id: str
    level_id: str
    description: str
    algorithms: tuple[str, ...]
    scenarios: tuple[BenchmarkScenario, ...]
    seeds: tuple[int, ...]
    repeats: int
    environment: str
    config_path: Path | None
    source_path: Path


def _positive(value: Any, field: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a positive integer") from exc
    if parsed <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return parsed


def _seeds(values: Any) -> tuple[int, ...]:
    if not isinstance(values, list) or not values:
        raise ValueError("suite.seeds must be a non-empty list")
    parsed = tuple(int(value) for value in values)
    if any(value < 0 for value in parsed) or len(parsed) != len(set(parsed)):
        raise ValueError("suite.seeds must contain distinct non-negative integers")
    return parsed


def load_benchmark_suite(path: str | Path) -> BenchmarkSuite:
    """Load a suite without resolving repository-relative experiment paths."""
    source_path = Path(path).resolve()
    try:
        data = yaml.safe_load(source_path.read_text(encoding="utf-8-sig"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"Cannot read benchmark suite {source_path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Benchmark suite {source_path} must contain a YAML mapping")
    suite_id = str(data.get("suite_id", "")).strip()
    level_id = str(data.get("level_id", "")).strip()
    if not suite_id or not level_id:
        raise ValueError("suite_id and level_id are required")
    algorithms = tuple(str(value) for value in data.get("algorithms", ()))
    if not algorithms or len(algorithms) != len(set(algorithms)):
        raise ValueError("suite.algorithms must be a non-empty list without duplicates")
    raw_scenarios = data.get("scenarios")
    if not isinstance(raw_scenarios, list) or not raw_scenarios:
        raise ValueError("suite.scenarios must be a non-empty list")
    scenarios: list[BenchmarkScenario] = []
    for index, value in enumerate(raw_scenarios, start=1):
        if not isinstance(value, dict):
            raise ValueError(f"suite.scenarios[{index}] must be a mapping")
        scenario_id = str(value.get("scenario_id", "")).strip()
        if not scenario_id:
            raise ValueError(f"suite.scenarios[{index}].scenario_id is required")
        tags = value.get("tags", [])
        if not isinstance(tags, list):
            raise ValueError(f"suite.scenarios[{index}].tags must be a list")
        scenarios.append(BenchmarkScenario(
            scenario_id=scenario_id,
            description=str(value.get("description", scenario_id)),
            item_count=_positive(value.get("item_count"), f"suite.scenarios[{index}].item_count"),
            container_count=_positive(value.get("container_count"), f"suite.scenarios[{index}].container_count"),
            tags=tuple(str(tag) for tag in tags),
        ))
    if len({value.scenario_id for value in scenarios}) != len(scenarios):
        raise ValueError("suite.scenarios scenario_id values must be unique")
    environment = str(data.get("environment", "local"))
    if environment not in {"local", "colab", "kaggle"}:
        raise ValueError("suite.environment must be local, colab, or kaggle")
    config_value = data.get("config")
    return BenchmarkSuite(
        suite_id=suite_id,
        level_id=level_id,
        description=str(data.get("description", "")),
        algorithms=algorithms,
        scenarios=tuple(scenarios),
        seeds=_seeds(data.get("seeds", [])),
        repeats=_positive(data.get("repeats", 1), "suite.repeats"),
        environment=environment,
        config_path=Path(str(config_value)) if config_value else None,
        source_path=source_path,
    )
