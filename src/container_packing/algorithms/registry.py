"""Registry of implemented optimization algorithms."""

from __future__ import annotations

from ..experiments.contracts import AlgorithmDefinition, LocalizedText

_ALGORITHMS = {
    "extreme_point_best_fit": AlgorithmDefinition(
        algorithm_id="extreme_point_best_fit",
        family="constructive_heuristic",
        description="Deterministic objective-aware Extreme-Point Best Fit Decreasing with level-declared orientation",
        supported_levels=("level_01", "level_02", "level_03", "level_04", "level_05"),
        local_friendly=True,
        display_name=LocalizedText(vi="Extreme Point — Best Fit Decreasing", en="Extreme Point — Best Fit Decreasing"),
        localized_description=LocalizedText(
            vi="Heuristic tham lam xét toàn bộ extreme point khả thi và chọn ứng viên tốt nhất theo điểm số mục tiêu.",
            en="Greedy heuristic that evaluates all feasible extreme points and chooses the best objective-aware candidate.",
        ),
    ),
    "extreme_point_ffd": AlgorithmDefinition(
        algorithm_id="extreme_point_ffd",
        family="constructive_heuristic",
        description="Deterministic Extreme-Point First-Fit Decreasing with level-declared orientation",
        supported_levels=("level_01", "level_02", "level_03", "level_04", "level_05"),
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
        supported_levels=("level_01", "level_02", "level_03", "level_04", "level_05"),
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
        supported_levels=("level_01", "level_02", "level_03", "level_04", "level_05"),
        local_friendly=True,
        display_name=LocalizedText(vi="Extreme Point — Simulated Annealing", en="Extreme Point — Simulated Annealing"),
        localized_description=LocalizedText(
            vi="Metaheuristic có seed, cho phép chấp nhận tạm thời nghiệm xấu theo xác suất Metropolis.",
            en="Seeded metaheuristic that can temporarily accept worse solutions using Metropolis probability.",
        ),
    ),
    "maximal_space_best_fit": AlgorithmDefinition(
        algorithm_id="maximal_space_best_fit",
        family="constructive_heuristic",
        description="Deterministic Maximal Empty Spaces Best Fit Decreasing with level-declared orientation",
        supported_levels=("level_01", "level_02", "level_03", "level_04"),
        local_friendly=True,
        display_name=LocalizedText(
            vi="Maximal Empty Spaces — Best Fit Decreasing",
            en="Maximal Empty Spaces — Best Fit Decreasing",
        ),
        localized_description=LocalizedText(
            vi="Heuristic tham lam duy trì các vùng trống cực đại bằng phép cắt sáu hướng và chọn space tốt nhất.",
            en="Greedy heuristic that maintains maximal empty spaces through six-way splitting and selects the best space.",
        ),
    ),
    "milp_big_m": AlgorithmDefinition(
        algorithm_id="milp_big_m",
        family="exact_milp",
        description="Exact sparse MILP with Big-M non-overlap and SciPy/HiGHS",
        supported_levels=("level_01", "level_02", "level_03"),
        local_friendly=True,
        display_name=LocalizedText(vi="MILP Big-M chính xác", en="Exact MILP Big-M"),
        localized_description=LocalizedText(
            vi="Mô hình MILP sparse với Big-M cho non-overlap, giải bằng SciPy/HiGHS.",
            en="Sparse Big-M non-overlap MILP solved with SciPy/HiGHS.",
        ),
    ),
    "extreme_point_ffd_nesting_fixture": AlgorithmDefinition(
        algorithm_id="extreme_point_ffd_nesting_fixture",
        family="experimental_constructive_heuristic",
        description="Experimental compound-root Extreme-Point FFD for explicitly declared nesting fixtures",
        supported_levels=("level_06",),
        local_friendly=True,
        display_name=LocalizedText(
            vi="Experimental — Compound Nesting FFD",
            en="Experimental — Compound Nesting FFD",
        ),
        localized_description=LocalizedText(
            vi="FFD thí nghiệm chỉ cho nesting metadata khai báo rõ; dùng compound root và validator độc lập.",
            en="Experimental FFD for explicitly declared nesting metadata using compound roots and independent validation.",
        ),
    ),
    "extreme_point_best_fit_nesting_fixture": AlgorithmDefinition(
        algorithm_id="extreme_point_best_fit_nesting_fixture",
        family="experimental_constructive_heuristic",
        description="Experimental compound-root Extreme-Point Best Fit for explicitly declared nesting fixtures",
        supported_levels=("level_06",),
        local_friendly=True,
        display_name=LocalizedText(
            vi="Experimental — Compound Nesting Best Fit",
            en="Experimental — Compound Nesting Best Fit",
        ),
        localized_description=LocalizedText(
            vi="Best Fit thử nghiệm dùng cùng compound projection và validator độc lập của FFD nesting.",
            en="Experimental Best Fit reusing the FFD nesting compound projection and independent validator.",
        ),
    ),
    "extreme_point_hill_climbing_nesting_fixture": AlgorithmDefinition(
        algorithm_id="extreme_point_hill_climbing_nesting_fixture",
        family="experimental_local_search",
        description="Compound-root Hill Climbing with fixed preconstructed nesting relations",
        supported_levels=("level_06",),
        local_friendly=True,
        display_name=LocalizedText(
            vi="Experimental — Compound Nesting Hill Climbing",
            en="Experimental — Compound Nesting Hill Climbing",
        ),
        localized_description=LocalizedText(
            vi="Hill Climbing destroy-and-repair trên compound roots; quan hệ nesting được giữ cố định.",
            en="Destroy-and-repair Hill Climbing over compound roots while nesting relations remain fixed.",
        ),
    ),
    "extreme_point_simulated_annealing_nesting_fixture": AlgorithmDefinition(
        algorithm_id="extreme_point_simulated_annealing_nesting_fixture",
        family="experimental_metaheuristic",
        description="Seeded compound-root Simulated Annealing with fixed preconstructed nesting relations",
        supported_levels=("level_06",),
        local_friendly=True,
        display_name=LocalizedText(
            vi="Experimental — Compound Nesting Simulated Annealing",
            en="Experimental — Compound Nesting Simulated Annealing",
        ),
        localized_description=LocalizedText(
            vi="Simulated Annealing có seed trên compound roots với profile p006; quan hệ nesting bất biến.",
            en="Seeded Simulated Annealing over compound roots using p006 while nesting relations remain fixed.",
        ),
    ),
    "level_07_fixture_validation_bundle": AlgorithmDefinition(
        algorithm_id="level_07_fixture_validation_bundle",
        family="fixture_validation",
        description="CLI-only Level 7 acceptance-fixture validation bundle; not a packing solver",
        supported_levels=("level_07",),
        local_friendly=True,
        display_name=LocalizedText(
            vi="Level 7 â€” Fixture validation bundle",
            en="Level 7 — Fixture validation bundle",
        ),
        localized_description=LocalizedText(
            vi="Chá»‰ táº¡o báº±ng chá»©ng validation cho fixture COG/cÃ¢n báº±ng Ä‘Ã£ Ä‘Ã³ng; khÃ´ng cháº¡y solver.",
            en="Produces frozen COG/balance fixture validation evidence only; it does not run a solver.",
        ),
    ),
    "extreme_point_best_fit_balance_fixture": AlgorithmDefinition(
        algorithm_id="extreme_point_best_fit_balance_fixture",
        family="experimental_constructive_heuristic",
        description="CLI-only Level 7 compound-root Best Fit with prospective COG tie-breaking",
        supported_levels=("level_07",), local_friendly=True,
        display_name=LocalizedText(vi="Experimental â€” Balance-aware Best Fit", en="Experimental â€” Balance-aware Best Fit"),
        localized_description=LocalizedText(
            vi="Best Fit fixture dùng COG dự kiến làm tie-break; cân bằng chỉ là ràng buộc validation cuối.",
            en="Fixture Best Fit uses prospective COG as a tie-break; balance remains a final validation constraint.",
        ),
    ),
    "extreme_point_best_fit_balance_baseline_fixture": AlgorithmDefinition(
        algorithm_id="extreme_point_best_fit_balance_baseline_fixture",
        family="experimental_constructive_heuristic",
        description="CLI-only Level 7 canonical Best Fit baseline for balance A/B acceptance",
        supported_levels=("level_07",), local_friendly=True,
        display_name=LocalizedText(vi="Experimental â€” Balance baseline Best Fit", en="Experimental â€” Balance baseline Best Fit"),
        localized_description=LocalizedText(
            vi="Comparator Best Fit không dùng COG score; final balance validator vẫn bắt buộc.",
            en="Best Fit comparator without COG scoring; final balance validation remains mandatory.",
        ),
    ),
    "extreme_point_ffd_balance_fixture": AlgorithmDefinition(
        algorithm_id="extreme_point_ffd_balance_fixture",
        family="experimental_constructive_heuristic",
        description="CLI-only Level 7 First Fit with prospective COG tie-breaking inside its first feasible container",
        supported_levels=("level_07",), local_friendly=True,
        display_name=LocalizedText(vi="Experimental â€” Balance-aware First Fit", en="Experimental â€” Balance-aware First Fit"),
        localized_description=LocalizedText(
            vi="Giữ First Fit theo container; COG chỉ chọn extreme point trong container khả thi đầu tiên.",
            en="Preserves First Fit container choice; COG selects only an extreme point within the first feasible container.",
        ),
    ),
    "extreme_point_ffd_balance_baseline_fixture": AlgorithmDefinition(
        algorithm_id="extreme_point_ffd_balance_baseline_fixture",
        family="experimental_constructive_heuristic",
        description="CLI-only Level 7 canonical First Fit baseline for balance A/B acceptance",
        supported_levels=("level_07",), local_friendly=True,
        display_name=LocalizedText(vi="Experimental â€” Balance baseline First Fit", en="Experimental â€” Balance baseline First Fit"),
        localized_description=LocalizedText(
            vi="Comparator First Fit không dùng COG; final balance validator vẫn bắt buộc.",
            en="Comparator First Fit without COG scoring; final balance validation remains mandatory.",
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
