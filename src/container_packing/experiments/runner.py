"""Generic registry-driven experiment runner."""

from __future__ import annotations

from .contracts import ExperimentRequest
from ..algorithms.registry import get_algorithm
from ..data_loader import load_config, merge_config
from ..dataset_usage import DatasetExecutionIntent, validate_dataset_usage
from ..levels.registry import get_level
from ..runtime.project import find_project_root


def run_experiment(request: ExperimentRequest):
    config = merge_config(load_config(request.config_path), dict(request.config_overrides or {}))
    validate_dataset_usage(find_project_root(__file__), config, DatasetExecutionIntent.SOLVER_EXPERIMENT)
    level = get_level(request.level_id)
    algorithm = get_algorithm(request.algorithm_id)
    if request.algorithm_id not in level.supported_algorithms or request.level_id not in algorithm.supported_levels:
        raise ValueError(f"{request.algorithm_id} is not compatible with {request.level_id}")
    return level.run(request)


def prepare_experiment(request: ExperimentRequest) -> dict:
    config = merge_config(load_config(request.config_path), dict(request.config_overrides or {}))
    validate_dataset_usage(find_project_root(__file__), config, DatasetExecutionIntent.DATA_PREPARATION)
    level = get_level(request.level_id)
    get_algorithm(request.algorithm_id)
    return level.prepare(request)
