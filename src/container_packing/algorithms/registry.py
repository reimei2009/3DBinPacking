"""Registry of implemented optimization algorithms."""

from __future__ import annotations

from ..experiments.contracts import AlgorithmDefinition

_ALGORITHMS = {
    "extreme_point_ffd": AlgorithmDefinition(
        algorithm_id="extreme_point_ffd",
        family="constructive_heuristic",
        description="Deterministic fixed-orientation Extreme-Point First-Fit Decreasing",
        supported_levels=("level_01",),
        local_friendly=True,
    ),
    "extreme_point_hill_climbing": AlgorithmDefinition(
        algorithm_id="extreme_point_hill_climbing",
        family="local_search",
        description="Extreme-Point FFD followed by deterministic destroy-and-repair hill climbing",
        supported_levels=("level_01",),
        local_friendly=True,
    ),
    "extreme_point_simulated_annealing": AlgorithmDefinition(
        algorithm_id="extreme_point_simulated_annealing",
        family="metaheuristic",
        description="Seeded Simulated Annealing over Extreme-Point destroy-and-repair neighborhoods",
        supported_levels=("level_01",),
        local_friendly=True,
    ),
    "milp_big_m": AlgorithmDefinition(
        algorithm_id="milp_big_m",
        family="exact_milp",
        description="Exact sparse MILP with Big-M non-overlap and SciPy/HiGHS",
        supported_levels=("level_01",),
        local_friendly=True,
    ),
}


def list_algorithms(*, level_id: str | None = None) -> tuple[AlgorithmDefinition, ...]:
    values = tuple(_ALGORITHMS[key] for key in sorted(_ALGORITHMS))
    if level_id is None:
        return values
    return tuple(value for value in values if level_id in value.supported_levels)


def get_algorithm(algorithm_id: str) -> AlgorithmDefinition:
    try:
        return _ALGORITHMS[algorithm_id]
    except KeyError as exc:
        available = ", ".join(sorted(_ALGORITHMS))
        raise ValueError(f"Algorithm {algorithm_id!r} is not implemented. Available: {available}") from exc
