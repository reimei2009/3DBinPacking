from __future__ import annotations

from pathlib import Path
import json

import pandas as pd

from container_packing.benchmarks.constructor_portfolio_acceptance import (
    SOURCE_COMMIT,
    evaluate_constructor_portfolio_acceptance,
    write_constructor_portfolio_acceptance,
)


STRATA = {"random": 60, "stress": 18, "prefix": 6}


def _artifacts(tmp_path: Path) -> tuple[list[Path], list[Path]]:
    portfolio_runs: list[Path] = []
    baseline_runs: list[Path] = []
    for level in ("level_04", "level_05"):
        for stratum, case_count in STRATA.items():
            portfolio = tmp_path / "portfolio" / level / stratum
            baseline = tmp_path / "baseline" / level / stratum
            benchmark = portfolio / "benchmark"
            baseline_benchmark = baseline / "benchmark"
            benchmark.mkdir(parents=True)
            baseline_benchmark.mkdir(parents=True)
            manifest = {
                "run_id": f"{level}-{stratum}-portfolio",
                "run_type": "benchmark_corpus",
                "level": level,
                "corpus_id": f"{level}_validated_constructor_portfolio_{stratum}_v1",
                "status": "SUCCESS",
                "git_commit": SOURCE_COMMIT,
                "git_dirty": False,
            }
            (portfolio / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8",
            )
            (baseline / "manifest.json").write_text(
                json.dumps({**manifest, "run_id": f"{level}-{stratum}-baseline"}),
                encoding="utf-8",
            )
            results: list[dict] = []
            comparisons: list[dict] = []
            determinism: list[dict] = []
            baseline_results: list[dict] = []
            for case_index in range(case_count):
                case_id = f"{stratum}-{case_index:03d}"
                checksum = f"items-{level}-{case_id}"
                improved = case_index == 0
                item_count = (20, 50, 100, 200, 300, 500)[case_index % 6]
                for repeat in (1, 2, 3):
                    selected_count = 2 if improved else 3
                    results.append({
                        "case_id": case_id,
                        "algorithm": "validated_best_fit_mes_portfolio",
                        "repeat": repeat,
                        "success": True,
                        "validation_valid": True,
                        "status": "FEASIBLE",
                        "official_objective": f"({selected_count}, {selected_count * 2000})",
                        "objective_value": float(selected_count),
                        "used_container_count": selected_count,
                        "total_container_cost": selected_count * 2000,
                        "placement_signature": f"signature-{case_id}",
                        "input_fingerprint": f"fingerprint-{level}-{case_id}",
                        "selected_item_ids_checksum": checksum,
                        "item_count": item_count,
                        "wall_runtime_seconds": 1.5,
                        "peak_rss_bytes": 110,
                    })
                    comparisons.append({
                        "case_id": case_id,
                        "repeat": repeat,
                        "selected_matches_best_child": True,
                        "outcome_vs_best_fit": "WIN" if improved else "TIE",
                        "runtime_ratio_vs_best_fit": 1.5,
                        "best_fit_validation": "VALID",
                        "best_fit_used_container_count": 3,
                        "best_fit_total_container_cost": 6000,
                        "mes_validation": "VALID",
                        "mes_used_container_count": selected_count,
                        "mes_total_container_cost": selected_count * 2000,
                        "selected_used_container_count": selected_count,
                        "incumbent_preserved": True,
                    })
                    baseline_results.append({
                        "algorithm": "extreme_point_best_fit",
                        "selected_item_ids_checksum": checksum,
                        "peak_rss_bytes": 100,
                    })
                determinism.append({"case_id": case_id, "deterministic": True})
            pd.DataFrame(results).to_csv(benchmark / "results.csv", index=False)
            pd.DataFrame(comparisons).to_csv(
                benchmark / "constructor_portfolio_comparison.csv", index=False,
            )
            pd.DataFrame(determinism).to_csv(
                benchmark / "determinism_evidence.csv", index=False,
            )
            pd.DataFrame(baseline_results).to_csv(
                baseline_benchmark / "results.csv", index=False,
            )
            portfolio_runs.append(portfolio)
            baseline_runs.append(baseline)
    return portfolio_runs, baseline_runs


def test_portfolio_evaluator_promotes_only_complete_passing_evidence(tmp_path: Path) -> None:
    portfolio, baseline = _artifacts(tmp_path)
    report = evaluate_constructor_portfolio_acceptance(portfolio, baseline)

    assert report["status"] == "PROMOTED"
    assert report["portfolio_ui_qualified"] is True
    assert report["levels"]["level_04"]["coverage"] == {
        "case_count": 84,
        "execution_count": 252,
        "valid_execution_count": 252,
        "deterministic_group_count": 84,
    }
    assert report["levels"]["level_05"]["runtime"]["median_ratio_vs_best_fit_child"] == 1.5


def test_portfolio_evaluator_fails_on_runtime_or_nondeterminism(tmp_path: Path) -> None:
    portfolio, baseline = _artifacts(tmp_path)
    comparison_path = portfolio[3] / "benchmark" / "constructor_portfolio_comparison.csv"
    comparison = pd.read_csv(comparison_path)
    comparison["runtime_ratio_vs_best_fit"] = 2.2
    comparison.to_csv(comparison_path, index=False)
    deterministic_path = portfolio[3] / "benchmark" / "determinism_evidence.csv"
    deterministic = pd.read_csv(deterministic_path)
    deterministic.loc[0, "deterministic"] = False
    deterministic.to_csv(deterministic_path, index=False)

    report = evaluate_constructor_portfolio_acceptance(portfolio, baseline)

    assert report["status"] == "NOT_PROMOTED"
    assert report["levels"]["level_05"]["status"] == "FAIL"
    assert any("deterministic gate failed" in value for value in report["errors"])
    assert any("runtime ratio exceeds" in value for value in report["errors"])


def test_portfolio_evaluator_fails_closed_on_missing_artifact(tmp_path: Path) -> None:
    portfolio, baseline = _artifacts(tmp_path)
    (portfolio[0] / "benchmark" / "constructor_portfolio_comparison.csv").unlink()

    report = evaluate_constructor_portfolio_acceptance(portfolio, baseline)

    assert report["status"] == "NOT_PROMOTED"
    assert any("artifact incomplete" in value for value in report["errors"])


def test_portfolio_evaluator_rejects_checksum_mismatch(tmp_path: Path) -> None:
    portfolio, baseline = _artifacts(tmp_path)
    initial = evaluate_constructor_portfolio_acceptance(portfolio, baseline)
    run_id = initial["source_evidence"][0]["run_id"]
    run_name = portfolio[0].name
    expected = {
        run_name: {
            **initial["source_evidence"][0]["checksums"],
            "results.csv": "0" * 64,
        }
    }

    report = evaluate_constructor_portfolio_acceptance(
        portfolio, baseline, expected_checksums=expected,
    )

    assert run_id
    assert report["status"] == "NOT_PROMOTED"
    assert any("checksum mismatch" in value for value in report["errors"])


def test_portfolio_evidence_writer_does_not_modify_source_runs(tmp_path: Path) -> None:
    portfolio, baseline = _artifacts(tmp_path)
    report = evaluate_constructor_portfolio_acceptance(portfolio, baseline)
    before_source = sorted(
        (root.name, path.relative_to(root))
        for root in (tmp_path / "portfolio", tmp_path / "baseline")
        for path in root.rglob("*")
    )

    json_path, markdown_path = write_constructor_portfolio_acceptance(
        report, tmp_path / "published" / "portfolio",
    )

    assert json_path.is_file() and markdown_path.is_file()
    assert "PROMOTED" in markdown_path.read_text(encoding="utf-8")
    after_source = sorted(
        (root.name, path.relative_to(root))
        for root in (tmp_path / "portfolio", tmp_path / "baseline")
        for path in root.rglob("*")
    )
    assert after_source == before_source
