from __future__ import annotations

from pathlib import Path
import json

import pandas as pd
import pytest

from container_packing.benchmarks.corpus import load_benchmark_corpus
from container_packing.benchmarks.cross_level_evidence import (
    attach_profiling_evidence,
    write_cross_level_evidence,
)
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


def test_cross_level_profile_evidence_is_diagnostic_and_writes_vietnamese_report(
    tmp_path: Path,
) -> None:
    profile_dirs = {}
    for level_id in ("level_03", "level_04", "level_05"):
        run_dir = tmp_path / level_id
        run_dir.mkdir()
        (run_dir / "profile_manifest.json").write_text(json.dumps({
            "run_id": f"profile_{level_id}",
            "run_type": "benchmark_profile",
            "status": "PASS",
            "eligible_for_benchmark_ranking": False,
            "selected_case_count": 1,
            "execution_count": 3,
        }), encoding="utf-8")
        (run_dir / "decision_gate.json").write_text(json.dumps({
            "reporting_median_wall_share": 0.1,
            "construction_median_wall_share": 0.7,
            "physical_constraint_share_of_profiled_solver_self_time": 0.5,
            "profiled_solver_category_shares": {
                "candidate_enumeration": 0.1,
                "overlap": 0.1,
                "exact_support": 0.3,
                "stackability": 0.0,
                "load_transfer": 0.0,
            },
            "priorities": ["spatial_or_contact_index"],
        }), encoding="utf-8")
        profile_dirs[level_id] = run_dir

    report = attach_profiling_evidence({
        "status": "PASS",
        "levels": ["level_03", "level_04", "level_05"],
        "reports": {
            level_id: {
                "status": "PASS", "case_count": 84, "execution_count": 756,
                "random_distribution_pairwise_vs_best_fit": [],
            }
            for level_id in ("level_03", "level_04", "level_05")
        },
        "runtime_ratio_medians": {"level_04_vs_03": 1.1, "level_05_vs_04": 1.2},
    }, profile_dirs)
    paths = write_cross_level_evidence(report, pd.DataFrame([{"case_id": "case"}]), tmp_path / "report")

    assert report["profiling"]["level_04"]["diagnostic_only"] is True
    assert all(path.is_file() for path in paths)
    markdown = paths[2].read_text(encoding="utf-8")
    assert "Acceptance phân phối và profiling Level 3–5" in markdown
    assert "không xếp hạng Level nào tốt hơn" in markdown


def test_cross_level_profile_evidence_rejects_rankable_profile(tmp_path: Path) -> None:
    profile_dirs = {}
    for level_id in ("level_03", "level_04", "level_05"):
        run_dir = tmp_path / level_id
        run_dir.mkdir()
        (run_dir / "profile_manifest.json").write_text(json.dumps({
            "run_type": "benchmark_profile", "status": "PASS",
            "eligible_for_benchmark_ranking": level_id == "level_04",
        }), encoding="utf-8")
        (run_dir / "decision_gate.json").write_text("{}", encoding="utf-8")
        profile_dirs[level_id] = run_dir

    with pytest.raises(ValueError, match="excluded from ranking"):
        attach_profiling_evidence({"status": "PASS"}, profile_dirs)
