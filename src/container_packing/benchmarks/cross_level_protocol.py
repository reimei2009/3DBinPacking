"""Shared Level 3--5 distribution benchmark protocol and evidence contract."""

from __future__ import annotations

from typing import Any


STRATA = ("random_distribution", "stress", "prefix_regression")


def expected_protocol(level_id: str) -> dict[str, dict[str, Any]]:
    """Return the immutable 84-case / 756-execution contract for one level."""
    if level_id not in {"level_03", "level_04", "level_05"}:
        raise ValueError("Cross-level distribution protocol supports level_03 through level_05")
    prefix = f"{level_id}_generated_1k_500"
    return {
        "random_distribution": {
            "corpus_id": f"{prefix}_random_v2_candidate",
            "case_count": 60,
            "execution_count": 540,
        },
        "stress": {
            "corpus_id": f"{prefix}_stress_v2_candidate",
            "case_count": 18,
            "execution_count": 162,
        },
        "prefix_regression": {
            "corpus_id": f"{prefix}_prefix_regression_v2",
            "case_count": 6,
            "execution_count": 54,
        },
    }
