from __future__ import annotations

from pathlib import Path

import pytest

from container_packing.benchmarks.corpus import load_benchmark_corpus
from container_packing.benchmarks.cross_level_protocol import expected_protocol


@pytest.mark.parametrize("level_id", ("level_03", "level_04", "level_05"))
def test_cross_level_distribution_matrix_is_complete_and_fair(root: Path, level_id: str) -> None:
    names = ("random", "stress", "prefix")
    corpora = {
        name: load_benchmark_corpus(
            root / "config" / level_id / "benchmarks" / f"distribution_{name}_v2_candidate.yaml",
            project_root=root,
        )
        for name in names
    }
    assert [len(corpora[name].cases) for name in names] == [60, 18, 6]
    assert all(corpus.repeats == 3 for corpus in corpora.values())
    protocol = expected_protocol(level_id)
    assert protocol["random_distribution"]["execution_count"] == 540
    assert protocol["stress"]["execution_count"] == 162
    assert protocol["prefix_regression"]["execution_count"] == 54

    for corpus in corpora.values():
        for case in corpus.cases:
            search = case.config_overrides["container_search"]
            assert search["enabled"] is True
            assert search["consolidation"]["enabled"] is False
            assert search["initial_used_container_count"] <= search["max_used_container_count"] <= 30
            assert set(case.algorithms) == {
                "extreme_point_best_fit", "extreme_point_ffd", "maximal_space_best_fit",
            }


def test_cross_level_protocol_rejects_unsupported_level() -> None:
    with pytest.raises(ValueError, match="level_03 through level_05"):
        expected_protocol("level_06")
