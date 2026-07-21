"""Registry of implemented optimization algorithms."""

from __future__ import annotations

from ..experiments.contracts import AlgorithmDefinition, LocalizedText

_ALGORITHMS = {
    "extreme_point_ffd": AlgorithmDefinition(
        algorithm_id="extreme_point_ffd",
        family="constructive_heuristic",
        description="Deterministic fixed-orientation Extreme-Point First-Fit Decreasing",
        supported_levels=("level_01",),
        local_friendly=True,
        display_name=LocalizedText(vi="Extreme Point — First Fit Decreasing", en="Extreme Point — First Fit Decreasing"),
        localized_description=LocalizedText(
            vi="Heuristic tham lam xác định, sắp kiện giảm dần và chọn extreme point khả thi đầu tiên.",
            en="Deterministic greedy heuristic that sorts items decreasingly and chooses the first feasible extreme point.",
        ),
    ),
    "extreme_point_hill_climbing": AlgorithmDefinition(
        algorithm_id="extreme_point_hill_climbing",
        family="local_search",
        description="Extreme-Point FFD followed by deterministic destroy-and-repair hill climbing",
        supported_levels=("level_01",),
        local_friendly=True,
        display_name=LocalizedText(vi="Extreme Point — Hill Climbing", en="Extreme Point — Hill Climbing"),
        localized_description=LocalizedText(
            vi="Tìm kiếm cục bộ destroy-and-repair, khởi tạo từ nghiệm Extreme-Point FFD.",
            en="Destroy-and-repair local search initialized from Extreme-Point FFD.",
        ),
    ),
    "extreme_point_simulated_annealing": AlgorithmDefinition(
        algorithm_id="extreme_point_simulated_annealing",
        family="metaheuristic",
        description="Seeded Simulated Annealing over Extreme-Point destroy-and-repair neighborhoods",
        supported_levels=("level_01",),
        local_friendly=True,
        display_name=LocalizedText(vi="Extreme Point — Simulated Annealing", en="Extreme Point — Simulated Annealing"),
        localized_description=LocalizedText(
            vi="Metaheuristic có seed, cho phép chấp nhận tạm thời nghiệm xấu theo xác suất Metropolis.",
            en="Seeded metaheuristic that can temporarily accept worse solutions using Metropolis probability.",
        ),
    ),
    "milp_big_m": AlgorithmDefinition(
        algorithm_id="milp_big_m",
        family="exact_milp",
        description="Exact sparse MILP with Big-M non-overlap and SciPy/HiGHS",
        supported_levels=("level_01",),
        local_friendly=True,
        display_name=LocalizedText(vi="MILP Big-M chính xác", en="Exact MILP Big-M"),
        localized_description=LocalizedText(
            vi="Mô hình MILP sparse với Big-M cho non-overlap, giải bằng SciPy/HiGHS.",
            en="Sparse Big-M non-overlap MILP solved with SciPy/HiGHS.",
        ),
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
