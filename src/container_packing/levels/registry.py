"""Registry of implemented mathematical level contracts."""

from __future__ import annotations

from pathlib import Path

from ..experiments.contracts import LevelDefinition
from . import level_01

_LEVELS = {
    "level_01": LevelDefinition(
        level_id="level_01",
        description="Fixed orientation; boundary, pairwise non-overlap, and payload constraints",
        default_config=Path("config/level_01/default.yaml"),
        supported_algorithms=(
            "milp_big_m", "extreme_point_ffd", "extreme_point_hill_climbing",
            "extreme_point_simulated_annealing",
        ),
        run=level_01.run,
        prepare=level_01.prepare,
        validate_run=level_01.validate_run,
    ),
}


def list_levels() -> tuple[LevelDefinition, ...]:
    return tuple(_LEVELS[key] for key in sorted(_LEVELS))


def get_level(level_id: str) -> LevelDefinition:
    try:
        return _LEVELS[level_id]
    except KeyError as exc:
        available = ", ".join(sorted(_LEVELS))
        raise ValueError(f"Level {level_id!r} is not implemented. Available: {available}") from exc
