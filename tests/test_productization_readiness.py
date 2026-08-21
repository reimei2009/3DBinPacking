from __future__ import annotations

from pathlib import Path
import json

import pandas as pd
import pytest
import yaml

from container_packing.algorithms.registry import get_algorithm
from container_packing.benchmarks.corpus import load_benchmark_corpus
from container_packing.benchmarks.distribution import build_repair_early_stop_comparison
from container_packing.levels.registry import get_level
from container_packing.productization.company_corpus import (
    load_company_corpus_contract,
    prepare_company_shadow_corpus,
)
from container_packing.productization.slo import evaluate_shadow_slo_frame
from container_packing.provenance import sha256_file


CONTRACT = "config/productization/company_like_shadow_v1.yaml"


def test_company_shadow_contract_is_governed_and_not_production(root: Path) -> None:
    contract = load_company_corpus_contract(CONTRACT, root=root)
    assert contract.evidence_class == "synthetic_calibrated_shadow"
    assert contract.scales == (100, 300, 500)
    assert set(contract.algorithms) == {
        "extreme_point_best_fit", "extreme_point_ffd", "maximal_space_best_fit",
    }
    assert contract.field_governance["safety_clearance"]["status"] == "unsupported"
    assert "không phải chứng nhận" in contract.safety_statement_vi


def test_company_shadow_contract_rejects_production_claim(root: Path, tmp_path: Path) -> None:
    payload = yaml.safe_load((root / CONTRACT).read_text(encoding="utf-8"))
    payload["evidence_class"] = "production_certified"
    path = tmp_path / "invalid.yaml"
    path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match="evidence_class"):
        load_company_corpus_contract(path, root=root)


def test_company_shadow_materialization_is_deterministic(root: Path, tmp_path: Path) -> None:
    contract = load_company_corpus_contract(CONTRACT, root=root)
    first = prepare_company_shadow_corpus(contract, output_dir_override=tmp_path / "a")
    second = prepare_company_shadow_corpus(contract, output_dir_override=tmp_path / "b")
    assert first["production_evidence"] is False
    assert first["item_count"] == 1000
    assert first["container_count"] == 500
    for name in ("solver_items.csv", "solver_containers.csv"):
        assert sha256_file(tmp_path / "a" / name) == sha256_file(tmp_path / "b" / name)


def test_company_shadow_matrix_has_declared_coverage(root: Path) -> None:
    corpus = load_benchmark_corpus(
        "config/level_02/benchmarks/company_like_shadow_manual.yaml",
        project_root=root,
    )
    assert len(corpus.cases) == 18
    assert sum(len(case.algorithms) for case in corpus.cases) * corpus.repeats == 162
    assert {case.item_count for case in corpus.cases} == {100, 300, 500}
    assert all(case.physical_inventory_count == 500 for case in corpus.cases)


def test_benchmark_algorithms_are_registered_and_bound(root: Path) -> None:
    corpus = load_benchmark_corpus(
        "config/level_02/benchmarks/company_like_shadow_manual.yaml",
        project_root=root,
    )
    level = get_level(corpus.level_id)
    for case in corpus.cases:
        for algorithm_id in case.algorithms:
            definition = get_algorithm(algorithm_id)
            assert algorithm_id in level.supported_algorithms
            assert corpus.level_id in definition.supported_levels


def test_inventory_ui_profiles_are_explicitly_research_only(root: Path) -> None:
    for level_id in ("level_02", "level_03", "level_04", "level_05"):
        payload = yaml.safe_load(
            (root / f"config/{level_id}/web_inventory_profiles.yaml").read_text(
                encoding="utf-8",
            )
        )
        profile = payload["profiles"]["items_1000_fleet_500_t10"]
        assert profile["evidence_class"] == "synthetic_research"
        assert profile["production_ready"] is False
    source = (root / "src/container_packing/web/streamlit_app.py").read_text(
        encoding="utf-8",
    )
    assert "không phải chứng nhận an toàn hoặc cam kết SLA production" in source


def _shadow_results(*, runtime: float = 1.0) -> pd.DataFrame:
    algorithms = ("extreme_point_best_fit", "extreme_point_ffd", "maximal_space_best_fit")
    rows = []
    for item_count in (100, 300, 500):
        for case_index in range(5):
            case_id = f"case_{item_count}_{case_index}"
            for algorithm in algorithms:
                for repeat in range(2):
                    rows.append({
                        "level": "level_02", "case_id": case_id,
                        "input_fingerprint": f"fp-{case_id}", "algorithm": algorithm,
                        "random_seed": 42, "success": True, "status": "FEASIBLE",
                        "validation_status": "VALID", "objective_value": "(4, 8000)",
                        "used_container_count": 4, "total_container_cost": 8000.0,
                        "item_count": item_count, "wall_runtime_seconds": runtime,
                        "peak_rss_bytes": 100_000_000,
                        "placement_signature": f"sig-{case_id}-{algorithm}",
                    })
    return pd.DataFrame(rows)


def test_shadow_slo_passes_only_with_complete_runtime_and_ui_evidence(root: Path) -> None:
    contract = load_company_corpus_contract(CONTRACT, root=root)
    report = evaluate_shadow_slo_frame(
        _shadow_results(), contract, ui_response_p95_seconds=0.5,
    )
    assert report["status"] == "SHADOW_PASS"
    assert report["production_evidence"] is False
    missing_ui = evaluate_shadow_slo_frame(_shadow_results(), contract)
    assert missing_ui["status"] == "SHADOW_NOT_READY"
    assert any("UI response" in value for value in missing_ui["errors"])


def test_shadow_slo_rejects_objective_on_failed_execution(root: Path) -> None:
    contract = load_company_corpus_contract(CONTRACT, root=root)
    frame = _shadow_results()
    frame.loc[0, ["success", "status"]] = [False, "TIME_LIMIT"]
    with pytest.raises(ValueError, match="must not carry"):
        evaluate_shadow_slo_frame(frame, contract, ui_response_p95_seconds=0.5)


def test_shadow_slo_file_evaluator_fails_closed_when_derived_evidence_is_missing(
    root: Path, tmp_path: Path,
) -> None:
    from container_packing.productization.slo import evaluate_shadow_slo

    contract = load_company_corpus_contract(CONTRACT, root=root)
    (tmp_path / "benchmark").mkdir()
    (tmp_path / "manifest.json").write_text(json.dumps({"status": "SUCCESS"}), encoding="utf-8")
    _shadow_results().to_csv(tmp_path / "benchmark/results.csv", index=False)
    with pytest.raises(ValueError, match="determinism and pairwise"):
        evaluate_shadow_slo(tmp_path, contract, ui_response_p95_seconds=0.5)


def test_repair_early_stop_ab_contract_has_48_paired_executions(root: Path) -> None:
    corpus = load_benchmark_corpus(
        "config/level_02/benchmarks/repair_early_stop_ab_manual.yaml",
        project_root=root,
    )
    assert len(corpus.cases) == 8
    assert sum(len(case.algorithms) for case in corpus.cases) * corpus.repeats == 48
    assert {case.item_count for case in corpus.cases} == {300, 500}
    assert {case.variant_id for case in corpus.cases} == {
        "repair_standard", "repair_early_stop",
    }


def test_repair_early_stop_comparison_is_paired_by_algorithm() -> None:
    rows = []
    for algorithm in ("extreme_point_best_fit", "extreme_point_ffd"):
        for variant, runtime, triggered in (
            ("repair_standard", 40.0, False),
            ("repair_early_stop", 25.0, True),
        ):
            for repeat in range(2):
                rows.append({
                    "level": "level_02", "case_id": f"{variant}_{algorithm}",
                    "input_fingerprint": "input", "comparison_input_fingerprint": "paired",
                    "comparison_group": "repair_case", "benchmark_variant_id": variant,
                    "algorithm": algorithm, "item_count": 300, "success": True,
                    "used_container_count": 8, "total_container_cost": 16000,
                    "wall_runtime_seconds": runtime,
                    "repair_early_stop_triggered": triggered,
                    "repair_objective_improvements_per_second": 0.02,
                })
    comparison = build_repair_early_stop_comparison(pd.DataFrame(rows))
    assert len(comparison) == 2
    assert comparison.algorithm.nunique() == 2
    assert comparison.quality_outcome.eq("UNCHANGED").all()
    assert comparison.incumbent_preserved.all()
    assert comparison.runtime_reduction_ratio.eq(0.375).all()
