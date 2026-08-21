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
from container_packing.productization.repair_evidence import (
    EXPECTED_CORPUS_ID,
    evaluate_repair_early_stop_v1,
)
from container_packing.productization.ui_latency import (
    UI_RESPONSE_METRIC_VERSION,
    collect_warm_rerun_samples,
    load_ui_response_evidence,
    summarize_ui_response_samples,
)
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
    assert contract.slo["minimum_ui_response_samples"] == 30
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


def test_shadow_slo_reads_validation_valid_from_real_corpus_schema(root: Path) -> None:
    contract = load_company_corpus_contract(CONTRACT, root=root)
    frame = _shadow_results().drop(columns=["validation_status"])
    frame["validation_valid"] = True
    report = evaluate_shadow_slo_frame(
        frame, contract, ui_response_p95_seconds=0.5,
    )
    assert report["status"] == "SHADOW_PASS"


def test_ui_measurement_excludes_warmups_and_uses_declared_quantile() -> None:
    observed: list[int] = []
    ticks = iter(float(value) for value in range(12))
    warmups, samples = collect_warm_rerun_samples(
        observed.append, warmups=2, samples=4, clock=lambda: next(ticks),
    )
    assert observed == [0, 1, 2, 3, 4, 5]
    assert warmups == [1.0, 1.0]
    assert samples == [1.0, 1.0, 1.0, 1.0]
    assert summarize_ui_response_samples(samples)["p95_seconds"] == 1.0


def test_ui_evidence_is_checksum_verified_and_requires_clean_source(
    tmp_path: Path,
) -> None:
    metrics_dir = tmp_path / "metrics"
    metrics_dir.mkdir()
    metrics = {
        "metric_version": UI_RESPONSE_METRIC_VERSION,
        "level_id": "level_02",
        "samples_seconds": [float(value) / 100 for value in range(30)],
    }
    metrics.update(summarize_ui_response_samples(metrics["samples_seconds"]))
    metrics_path = metrics_dir / "ui_response.json"
    metrics_path.write_text(json.dumps(metrics), encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest = {
        "run_type": "ui_response_profile", "status": "SUCCESS",
        "level": "level_02", "metric_version": UI_RESPONSE_METRIC_VERSION,
        "git_dirty": False, "metrics_sha256": sha256_file(metrics_path),
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    evidence = load_ui_response_evidence(
        tmp_path, expected_level="level_02", minimum_samples=30,
    )
    assert evidence["metrics"]["sample_count"] == 30

    metrics_path.write_text(json.dumps({**metrics, "p95_seconds": 99}), encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        load_ui_response_evidence(
            tmp_path, expected_level="level_02", minimum_samples=30,
        )


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


def test_repair_signal_diagnostic_has_18_full_repair_executions(root: Path) -> None:
    corpus = load_benchmark_corpus(
        "config/level_02/benchmarks/repair_signal_diagnostic_manual.yaml",
        project_root=root,
    )
    assert len(corpus.cases) == 3
    assert sum(len(case.algorithms) for case in corpus.cases) * corpus.repeats == 18
    assert {case.item_count for case in corpus.cases} == {300, 500}
    for case in corpus.cases:
        consolidation = case.config_overrides["container_search"]["consolidation"]
        assert consolidation["signal_telemetry_enabled"] is True
        assert consolidation["early_stop"]["enabled"] is False


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


def test_repair_v1_evidence_is_fail_closed_and_records_regression(
    tmp_path: Path,
) -> None:
    benchmark = tmp_path / "benchmark"
    benchmark.mkdir()
    (tmp_path / "manifest.json").write_text(json.dumps({
        "corpus_id": EXPECTED_CORPUS_ID, "status": "SUCCESS",
        "git_dirty": False, "git_commit": "source", "run_id": "repair-run",
    }), encoding="utf-8")
    rows = []
    deterministic_rows = []
    for case_index in range(8):
        case_id = f"case-{case_index}"
        algorithm = (
            "extreme_point_best_fit" if case_index % 2 == 0 else "extreme_point_ffd"
        )
        for repeat in range(3):
            rows.append({
                "case_id": case_id, "algorithm": algorithm, "success": True,
                "validation_valid": True, "official_objective": "[4, 8000]",
            })
        for other_algorithm in (algorithm, "companion"):
            deterministic_rows.append({
                "case_id": case_id, "algorithm": other_algorithm,
                "deterministic": True,
            })
    pd.DataFrame(rows * 2).iloc[:48].to_csv(
        benchmark / "results.csv", index=False,
    )
    pd.DataFrame(deterministic_rows).to_csv(
        benchmark / "determinism_evidence.csv", index=False,
    )
    comparison = pd.DataFrame([{
        "algorithm": "extreme_point_best_fit",
        "comparison_group": f"group-{index}", "item_count": 500,
        "standard_containers": 4, "early_stop_containers": 5 if index == 0 else 4,
        "standard_cost": 8000.0, "early_stop_cost": 10000.0 if index == 0 else 8000.0,
        "runtime_reduction_ratio": 0.5,
        "quality_outcome": "REGRESSION" if index == 0 else "UNCHANGED",
    } for index in range(8)])
    comparison.to_csv(benchmark / "repair_early_stop_comparison.csv", index=False)

    report = evaluate_repair_early_stop_v1(tmp_path)
    assert report["decision"] == "NOT_PROMOTED"
    assert report["quality_outcomes"] == {
        "IMPROVED": 0, "UNCHANGED": 7, "REGRESSION": 1,
    }
    (benchmark / "repair_early_stop_comparison.csv").unlink()
    with pytest.raises(ValueError, match="requires manifest"):
        evaluate_repair_early_stop_v1(tmp_path)
