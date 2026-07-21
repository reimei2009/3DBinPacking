"""Generic registry-driven experiment runner."""

from __future__ import annotations

from .contracts import ExperimentRequest
from ..algorithms.registry import get_algorithm
from ..levels.registry import get_level


def run_experiment(request: ExperimentRequest):
    level = get_level(request.level_id)
    algorithm = get_algorithm(request.algorithm_id)
    if request.algorithm_id not in level.supported_algorithms or request.level_id not in algorithm.supported_levels:
        raise ValueError(f"{request.algorithm_id} is not compatible with {request.level_id}")
    return level.run(request)


def prepare_experiment(request: ExperimentRequest) -> dict:
    level = get_level(request.level_id)
    get_algorithm(request.algorithm_id)
    return level.prepare(request)
