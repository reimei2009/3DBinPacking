import json
from math import ceil
from pathlib import Path

import pandas as pd
import yaml
import pytest

from container_packing.benchmarks import (
    load_benchmark_catalog,
    run_benchmark,
    run_benchmark_corpus,
)
from container_packing.benchmarks.runner import _aggregate, annotate_reference_gaps
from container_packing.benchmarks.fingerprint import (
    experiment_fingerprint,
    semantic_input_fingerprint,
)
from container_packing.benchmarks.suites import BenchmarkScenario, load_benchmark_suite
from container_packing.benchmarks.corpus import (
    build_selection_overlap,
    load_benchmark_corpus,
)
from container_packing.data_loader import load_config
from container_packing.dataset_usage import DatasetExecutionIntent, validate_dataset_usage


def test_benchmark_rejects_failed_row_that_leaks_objective() -> None:
    frame = pd.DataFrame([{
        "level": "level_01",
        "algorithm": "bad",
        "item_count": 1,
        "container_count": 1,
        "success": False,
        "objective_value": 123.0,
        "used_container_count": 1,
        "total_container_cost": 10.0,
    }])
    with pytest.raises(ValueError, match="must not report objective"):
        _aggregate(frame)


def test_reference_semantics_cover_exact_observed_infeasible_and_unavailable() -> None:
    rows = [
        ("exact", "milp", "OPTIMAL", True, 1, 10.0, 100.0),
        ("observed", "heuristic", "FEASIBLE", True, 2, 20.0, 200.0),
        ("infeasible", "milp", "INFEASIBLE", False, None, None, None),
        ("unavailable", "heuristic", "INFEASIBLE_HEURISTIC", False, None, None, None),
    ]
    frame = pd.DataFrame([
        {
            "case_id": case_id,
            "algorithm": algorithm,
            "status": status,
            "success": success,
            "official_objective": ({"used_container_count": count} if success else None),
            "used_container_count": count,
            "total_container_cost": cost,
            "objective_value": objective,
            "algorithm_runtime_seconds": 1.0,
        }
        for case_id, algorithm, status, success, count, cost, objective in rows
    ])
    annotated = annotate_reference_gaps(frame, instance_keys=("case_id",))
    kinds = dict(zip(annotated["case_id"], annotated["reference_kind"]))
    assert kinds == {
        "exact": "proven_optimal",
        "observed": "best_observed",
        "infeasible": "proven_infeasible",
        "unavailable": "unavailable",
    }


def test_benchmark_rejects_failed_row_that_leaks_secondary_score() -> None:
    import pandas as pd

    frame = pd.DataFrame([{
        "level": "level_02",
        "algorithm": "maximal_space_best_fit",
        "item_count": 1,
        "container_count": 1,
        "random_seed": 42,
        "repeat": 1,
        "success": False,
        "status": "TIME_LIMIT",
        "algorithm_runtime_seconds": 1.0,
        "wall_runtime_seconds": 1.0,
        "objective_value": None,
        "official_objective": None,
        "official_secondary_search_score": {
            "utilization_concentration": 0.5,
            "internal_void_ratio": 0.1,
            "minimum_support_margin": 0.2,
        },
        "used_container_count": None,
        "total_container_cost": None,
        "placement_signature": None,
    }])

    with pytest.raises(ValueError, match="must not report objective quality"):
        _aggregate(frame)


def test_benchmark_rejects_failed_row_that_leaks_diagnostic_score() -> None:
    frame = pd.DataFrame([{
        "level": "level_02", "algorithm": "extreme_point_best_fit",
        "item_count": 1, "container_count": 1, "random_seed": 42, "repeat": 1,
        "success": False, "status": "TIME_LIMIT", "algorithm_runtime_seconds": 1.0,
        "wall_runtime_seconds": 1.0, "objective_value": None,
        "official_objective": None, "official_secondary_search_score": None,
        "diagnostic_secondary_search_score": {"utilization_concentration": 0.5},
        "used_container_count": None, "total_container_cost": None,
        "placement_signature": None,
    }])

    with pytest.raises(ValueError, match="must not report objective quality"):
        _aggregate(frame)


def test_semantic_fingerprint_covers_rules_while_algorithm_parameters_are_separate(
    tmp_path: Path,
) -> None:
    rules = tmp_path / "rules.yaml"
    rules.write_text("minimum_ratio: 0.8\n", encoding="utf-8")
    scenario = BenchmarkScenario("s", "semantic", 1, 1)
    config = {
        "validation": {"rules_file": str(rules)},
        "algorithms": {"extreme_point_ffd": {"subset_enumeration_limit": 3}},
    }
    kwargs = {
        "level_id": "level_02",
        "scenario": scenario,
        "config": config,
        "root": tmp_path,
        "selection": {"selected_item_ids_checksum": "items"},
        "dataset_usage": None,
    }
    first = semantic_input_fingerprint(**kwargs)
    rules.write_text("minimum_ratio: 0.9\n", encoding="utf-8")
    second = semantic_input_fingerprint(**kwargs)
    assert first != second

    config["algorithms"]["extreme_point_ffd"]["subset_enumeration_limit"] = 4
    assert semantic_input_fingerprint(**kwargs) == second
    assert experiment_fingerprint(
        input_fingerprint=second,
        algorithm_id="extreme_point_ffd",
        random_seed=42,
        config=config,
    ) != experiment_fingerprint(
        input_fingerprint=second,
        algorithm_id="extreme_point_ffd",
        random_seed=7,
        config=config,
    )


def test_configured_corpus_keeps_exact_reference_and_infeasibility_semantics(
    root: Path, tmp_path: Path,
) -> None:
    config = load_config(root / "config/level_01/default.yaml")
    config["paths"]["raw_items_csv"] = str(
        root / "data/raw/dataset_small_items_original.csv"
    )
    config["paths"]["processed_dir"] = str(tmp_path / "processed/level_01")
    config["paths"]["manifest_json"] = str(
        tmp_path / "processed/level_01/latest_manifest.json"
    )
    config["paths"]["output_root"] = str(tmp_path / "outputs")
    config_path = tmp_path / "level_01.yaml"
    config_path.write_text(
        yaml.safe_dump(config, sort_keys=False), encoding="utf-8",
    )
    corpus_path = tmp_path / "corpus.yaml"
    corpus_path.write_text(yaml.safe_dump({
        "schema_version": "1.0",
        "corpus_id": "test_corpus",
        "level_id": "level_01",
        "environment": "local",
        "seeds": [42],
        "repeats": 1,
        "default_config": str(config_path),
        "cases": [
            {
                "case_id": "feasible_i1_c1",
                "group": "small",
                "difficulty": "easy",
                "item_count": 1,
                "container_count": 1,
                "expected_outcome": "feasible",
                "algorithms": ["milp_big_m", "extreme_point_ffd"],
            },
            {
                "case_id": "infeasible_i10_c1",
                "group": "small",
                "difficulty": "infeasible",
                "item_count": 10,
                "container_count": 1,
                "expected_outcome": "infeasible",
                "algorithms": ["milp_big_m", "extreme_point_ffd"],
            },
        ],
    }, sort_keys=False), encoding="utf-8")

    result = run_benchmark_corpus(corpus_path, project_root=root)

    assert result.successful
    assert len(result.results) == 4
    assert result.results.expectation_met.all()
    assert set(result.references.reference_kind) == {
        "proven_optimal", "proven_infeasible",
    }
    assert result.results[
        result.results.case_id == "feasible_i1_c1"
    ].objective_gap_percent.eq(0).all()
    assert set(
        result.ranking[result.ranking.case_id == "feasible_i1_c1"]["rank"]
    ) == {1, 2}
    for name in (
        "case_catalog.csv", "results.csv", "summary.csv", "ranking.csv",
        "references.csv", "case_features.csv", "pairwise_outcomes.csv",
        "distribution_summary.csv", "determinism_evidence.csv",
        "repair_comparison.csv", "selection_overlap.csv",
    ):
        assert (result.run_dir / "benchmark" / name).is_file()
    manifest = json.loads(
        (result.run_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["run_type"] == "benchmark_corpus"
    assert manifest["case_count"] == 2
    assert manifest["execution_count"] == 4
    assert manifest["successful_execution_count"] == 4


def _recovery_fixture(
    root: Path, tmp_path: Path,
) -> tuple[Path, Path]:
    config = load_config(root / "config/level_01/default.yaml")
    config["paths"]["raw_items_csv"] = str(
        root / "data/raw/dataset_small_items_original.csv"
    )
    config["paths"]["processed_dir"] = str(tmp_path / "processed/level_01")
    config["paths"]["manifest_json"] = str(
        tmp_path / "processed/level_01/latest_manifest.json"
    )
    config["paths"]["output_root"] = str(tmp_path / "outputs")
    config_path = tmp_path / "recovery_level_01.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    corpus_path = tmp_path / "recovery_corpus.yaml"
    corpus_path.write_text(yaml.safe_dump({
        "schema_version": "1.0", "corpus_id": "recovery_corpus",
        "level_id": "level_01", "environment": "local",
        "seeds": [42], "repeats": 2, "default_config": str(config_path),
        "cases": [{
            "case_id": "recovery_i1_c1", "item_count": 1,
            "container_count": 1, "expected_outcome": "feasible",
            "algorithms": ["extreme_point_ffd"],
        }],
    }, sort_keys=False), encoding="utf-8")
    return config_path, corpus_path


def test_corpus_recovery_reuses_valid_rows_and_reruns_only_failure(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _config_path, corpus_path = _recovery_fixture(root, tmp_path)
    source = run_benchmark_corpus(corpus_path, project_root=root)
    results_path = source.run_dir / "benchmark/results.csv"
    results = pd.read_csv(results_path)
    failed_index = results.index[results["repeat"].eq(2)][0]
    for column, value in {
        "status": "ERROR", "success": False, "validation_valid": False,
        "expectation_met": False, "objective_value": None,
        "official_objective": None, "used_container_count": None,
        "total_container_cost": None, "placement_signature": None,
    }.items():
        results.loc[failed_index, column] = value
    results.to_csv(results_path, index=False)

    import container_packing.benchmarks.corpus as corpus_module
    original_execute = corpus_module.execute_experiment_case
    executed: list[int] = []

    def tracking_execute(request, repeat_index):
        executed.append(repeat_index)
        return original_execute(request, repeat_index)

    monkeypatch.setattr(corpus_module, "execute_experiment_case", tracking_execute)
    recovered = run_benchmark_corpus(
        corpus_path, project_root=root, recover_from=source.run_dir,
        rerun_failed_only=True,
    )

    assert executed == [2]
    assert recovered.successful
    assert recovered.results["success"].all()
    assert set(recovered.results["recovery_execution_action"]) == {
        "reused_valid", "rerun_failed",
    }
    manifest = json.loads(
        (recovered.run_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["recovery_mode"] is True
    assert manifest["recovery"]["reused_execution_count"] == 1
    assert manifest["recovery"]["rerun_execution_count"] == 1
    assert manifest["recovery"]["run_id"] == source.run_id


def test_corpus_recovery_reuses_completed_event_log_after_postprocessing_crash(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _config_path, corpus_path = _recovery_fixture(root, tmp_path)
    source = run_benchmark_corpus(corpus_path, project_root=root)
    (source.run_dir / "benchmark/results.csv").unlink()
    (source.run_dir / "manifest.json").unlink()

    monkeypatch.setattr(
        "container_packing.benchmarks.corpus.execute_experiment_case",
        lambda *_args, **_kwargs: pytest.fail("completed executions must be reused"),
    )
    recovered = run_benchmark_corpus(
        corpus_path, project_root=root, recover_from=source.run_dir,
        rerun_failed_only=True,
    )

    assert recovered.successful
    assert set(recovered.results["recovery_execution_action"]) == {"reused_valid"}
    manifest = json.loads(
        (recovered.run_dir / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["recovery"]["source_kind"] == "completed_event_log"
    assert manifest["recovery"]["reused_execution_count"] == 2


def test_corpus_recovery_rejects_provenance_mismatch_before_execution(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _config_path, corpus_path = _recovery_fixture(root, tmp_path)
    source = run_benchmark_corpus(corpus_path, project_root=root)
    payload = yaml.safe_load(corpus_path.read_text(encoding="utf-8"))
    payload["cases"][0]["item_count"] = 2
    corpus_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    monkeypatch.setattr(
        "container_packing.benchmarks.corpus.execute_experiment_case",
        lambda *_args, **_kwargs: pytest.fail("executor must not run on provenance mismatch"),
    )

    with pytest.raises(ValueError, match="provenance does not match"):
        run_benchmark_corpus(
            corpus_path, project_root=root, recover_from=source.run_dir,
            rerun_failed_only=True,
        )


def test_corpus_case_supports_selection_and_dataset_identity(root: Path, tmp_path: Path) -> None:
    corpus_path = tmp_path / "corpus.yaml"
    corpus_path.write_text(yaml.safe_dump({
        "schema_version": "1.0", "corpus_id": "selection_corpus", "level_id": "level_02",
        "seeds": [42], "repeats": 1,
        "default_config": "config/level_02/default.yaml",
        "cases": [{
            "case_id": "random_case", "item_count": 2, "container_count": 2,
            "expected_outcome": "feasible", "algorithms": ["extreme_point_ffd"],
            "item_selection": "stable_random", "selection_seed": 101,
            "dataset_family": "canonical", "scale_bucket": "micro",
        }],
    }, sort_keys=False), encoding="utf-8")
    corpus = load_benchmark_corpus(corpus_path, project_root=root)
    case = corpus.cases[0]
    assert case.item_selection_strategy == "stable_random"
    assert case.item_selection_seed == 101
    assert case.dataset_family == "canonical"
    assert case.scale_bucket == "micro"


def test_corpus_case_preserves_config_overrides_for_its_resolved_input(root: Path, tmp_path: Path) -> None:
    corpus_path = tmp_path / "corpus.yaml"
    overrides = {"paths": {"raw_items_csv": "data/interim/mpv/items.csv"}}
    corpus_path.write_text(yaml.safe_dump({
        "schema_version": "1.0", "corpus_id": "override_corpus", "level_id": "level_02",
        "seeds": [42], "repeats": 1, "default_config": "config/level_02/default.yaml",
        "cases": [{
            "case_id": "mpv_case", "item_count": 2, "container_count": 2,
            "expected_outcome": "feasible", "algorithms": ["extreme_point_ffd"],
            "config_overrides": overrides,
        }],
    }, sort_keys=False), encoding="utf-8")

    corpus = load_benchmark_corpus(corpus_path, project_root=root)

    assert corpus.cases[0].config_overrides == overrides


def test_mpv_corpus_rejects_container_limit_above_materialized_inventory(
    root: Path, tmp_path: Path,
) -> None:
    corpus_path = tmp_path / "mpv_invalid_inventory.yaml"
    corpus_path.write_text(yaml.safe_dump({
        "schema_version": "1.0", "corpus_id": "mpv_invalid_inventory",
        "level_id": "level_02", "seeds": [42], "repeats": 1,
        "default_config": "config/level_02/experiments/mpv_fixed_orientation_acceptance.yaml",
        "cases": [{
            "case_id": "mpv_c01_n020_i01", "item_count": 20,
            "container_count": 20, "expected_outcome": "feasible",
            "algorithms": ["extreme_point_ffd"],
            "dataset_family": "mpv_fixed_orientation_exact_support",
            "config_overrides": {
                "container_search": {"max_used_container_count": 100},
            },
        }],
    }, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="allows 100 containers.*only 20"):
        load_benchmark_corpus(corpus_path, project_root=root)


def test_level1_gap_fill_screening_suite_has_ten_fair_seeded_profiles(
    root: Path,
) -> None:
    suite = load_benchmark_suite(
        root / "config/level_01/benchmarks/ep_ffd_gap_fill_screening_i20_c5_local.yaml"
    )

    assert suite.suite_id == "level_01_ep_ffd_gap_fill_screening_i20_c5_v1"
    assert suite.algorithms == ("extreme_point_ffd", "extreme_point_ffd_gap_fill")
    assert suite.seeds == (42,)
    assert suite.repeats == 1
    assert len(suite.scenarios) == 10
    assert [value.item_selection_seed for value in suite.scenarios] == list(range(101, 111))
    assert all(value.item_selection_strategy == "stable_random" for value in suite.scenarios)
    assert all((value.item_count, value.container_count) == (20, 5) for value in suite.scenarios)
    assert all(value.algorithm_ids == suite.algorithms for value in suite.scenarios)
    assert all("fixed_subset" in value.tags for value in suite.scenarios)


def test_level2_quick_and_distribution_protocols_use_generated_qualified_source(root: Path) -> None:
    quick = load_benchmark_corpus(
        root / "config/level_02/benchmarks/ui_quick_generated_1k_500_v2.yaml",
        project_root=root,
    )
    corpus = load_benchmark_corpus(
        root / "config/level_02/benchmarks/generated_1k_500_distribution_corpus.yaml",
        project_root=root,
    )
    assert len(quick.cases) == 6
    assert sum(len(case.algorithms) for case in quick.cases) == 18
    assert {case.item_count for case in quick.cases} == {20, 50, 100}
    assert all(case.dataset_family == "generated_1k_500_canonical" for case in quick.cases)
    assert {case.item_count for case in corpus.cases} == {20, 50, 100, 200, 300, 500}
    assert {case.item_selection_seed for case in corpus.cases if case.item_selection_strategy == "stable_random"} == {101, 202, 303}
    assert len(corpus.cases) == 24
    assert corpus.repeats == 2
    assert sum(len(case.algorithms) for case in corpus.cases) * corpus.repeats == 144
    expected_algorithms = {
        "extreme_point_best_fit", "extreme_point_ffd", "maximal_space_best_fit",
    }
    deadlines = {20: 30, 50: 30, 100: 60, 200: 90, 300: 90, 500: 120}
    for case in corpus.cases:
        search = case.config_overrides["container_search"]
        assert set(case.algorithms) == expected_algorithms
        assert search["initial_used_container_count"] == case.container_count
        assert search["max_used_container_count"] == max(
            case.container_count + 2, ceil(case.container_count * 1.6),
        )
        assert search["time_limit_seconds"] == deadlines[case.item_count]
        assert search["consolidation"]["enabled"] is False


def test_level2_stratified_candidate_materializes_84_cases_and_756_executions(
    root: Path,
) -> None:
    paths = {
        "random_distribution": (
            "generated_1k_500_random_candidate.yaml", 60, 540,
        ),
        "stress": ("generated_1k_500_stress_candidate.yaml", 18, 162),
        "prefix_regression": (
            "generated_1k_500_prefix_regression.yaml", 6, 54,
        ),
    }
    cases = []
    executions = 0
    for stratum, (filename, expected_cases, expected_executions) in paths.items():
        corpus = load_benchmark_corpus(
            root / "config/level_02/benchmarks" / filename,
            project_root=root,
        )
        assert len(corpus.cases) == expected_cases
        assert corpus.repeats == 3
        assert {case.benchmark_stratum for case in corpus.cases} == {stratum}
        actual_executions = (
            sum(len(case.algorithms) for case in corpus.cases) * corpus.repeats
        )
        assert actual_executions == expected_executions
        cases.extend(corpus.cases)
        executions += actual_executions
    assert len(cases) == 84
    assert executions == 756


def test_level2_stratified_candidate_uses_fair_limits_and_selection_contract(
    root: Path,
) -> None:
    random = load_benchmark_corpus(
        root / "config/level_02/benchmarks/generated_1k_500_random_candidate.yaml",
        project_root=root,
    )
    stress = load_benchmark_corpus(
        root / "config/level_02/benchmarks/generated_1k_500_stress_candidate.yaml",
        project_root=root,
    )
    prefix = load_benchmark_corpus(
        root / "config/level_02/benchmarks/generated_1k_500_prefix_regression.yaml",
        project_root=root,
    )
    assert {case.item_selection_seed for case in random.cases} == {
        101, 211, 307, 401, 503, 601, 701, 809, 907, 1009,
    }
    assert {case.item_selection_strategy for case in stress.cases} == {
        "largest_volume", "heaviest", "payload_pressure",
    }
    deadlines = {20: 30, 50: 30, 100: 60, 200: 90, 300: 90, 500: 120}
    for case in (*random.cases, *stress.cases):
        search = case.config_overrides["container_search"]
        assert case.aggregate_lower_bound == max(
            case.volume_lower_bound, case.payload_lower_bound,
        )
        assert case.container_count == case.aggregate_lower_bound
        assert search["initial_used_container_count"] == case.aggregate_lower_bound
        assert search["max_used_container_count"] == min(
            500,
            max(case.aggregate_lower_bound + 2, ceil(case.aggregate_lower_bound * 1.6)),
        )
        assert search["time_limit_seconds"] == deadlines[case.item_count]
        assert search["consolidation"]["enabled"] is False
        assert len(case.algorithms) == 3
        assert case.planned_selected_item_ids_checksum

    for corpus in (random, stress, prefix):
        checksums_by_scale: dict[int, set[str]] = {}
        for case in corpus.cases:
            checksums_by_scale.setdefault(case.item_count, set()).add(
                str(case.planned_selected_item_ids_checksum),
            )
        for item_count, checksums in checksums_by_scale.items():
            assert len(checksums) == sum(
                candidate.item_count == item_count for candidate in corpus.cases
            )


def test_selection_overlap_is_explicit_and_does_not_claim_independence() -> None:
    overlap = build_selection_overlap({
        "a": {
            "case_id": "a", "benchmark_stratum": "random_distribution",
            "item_count": 3, "item_selection_strategy": "stable_random",
            "item_selection_seed": 101, "selected_item_ids": ("A", "B", "C"),
        },
        "b": {
            "case_id": "b", "benchmark_stratum": "random_distribution",
            "item_count": 3, "item_selection_strategy": "stable_random",
            "item_selection_seed": 211, "selected_item_ids": ("B", "C", "D"),
        },
    })
    assert len(overlap) == 1
    assert overlap.iloc[0].intersection_count == 2
    assert overlap.iloc[0].overlap_fraction_of_case == pytest.approx(2 / 3)
    assert overlap.iloc[0].jaccard_similarity == pytest.approx(0.5)


def test_matrix_corpus_e2e_keeps_same_input_for_algorithms(
    root: Path, tmp_path: Path,
) -> None:
    corpus_path = tmp_path / "matrix_smoke.yaml"
    corpus_path.write_text(yaml.safe_dump({
        "schema_version": "1.1", "corpus_id": "matrix_smoke",
        "level_id": "level_02", "seeds": [42], "repeats": 1,
        "default_config": "config/level_02/default.yaml",
        "matrix": {
            "case_prefix": "smoke", "benchmark_stratum": "random_distribution",
            "dataset_family": "matrix_smoke", "algorithms": [
                "extreme_point_best_fit", "extreme_point_ffd",
            ],
            "scales": [{"item_count": 1, "time_limit_seconds": 30, "scale_bucket": "micro"}],
            "selections": [{"selection_id": "random", "item_selection": "stable_random", "selection_seeds": [101]}],
            "config_overrides": {"paths": {"output_root": str(tmp_path / "outputs")}},
        },
    }, sort_keys=False), encoding="utf-8")

    result = run_benchmark_corpus(corpus_path, project_root=root)

    assert result.successful
    assert len(result.results) == 2
    assert result.results.input_fingerprint.nunique() == 1
    assert result.results.selected_item_ids_checksum.nunique() == 1
    assert result.results.validation_valid.all()
    assert (result.run_dir / "benchmark/selection_overlap.csv").is_file()


def test_level2_benchmark_catalog_separates_canonical_academic_and_research(root: Path) -> None:
    catalog = load_benchmark_catalog(
        root / "config/level_02/benchmarks/registry.yaml", project_root=root,
    )
    assert catalog.get("level_02_generated_canonical_v1").kind == "canonical"
    assert catalog.get("level_02_mpv_acceptance_v1").kind == "academic"
    assert catalog.get("level_02_repair_ab_v1").kind == "research"
    assert catalog.get("level_02_generated_random_v2_candidate").kind == "research"
    legacy = catalog.get("level_02_capacity_repair_legacy_v1")
    assert legacy.kind == "superseded"
    assert legacy.replacement_id == "level_02_repair_ab_v1"


def test_level2_repair_corpus_has_controlled_treatment_pairs(root: Path) -> None:
    corpus = load_benchmark_corpus(
        root / "config/level_02/benchmarks/canonical_repair_ab_corpus.yaml",
        project_root=root,
    )
    assert len(corpus.cases) == 12
    assert sum(len(case.algorithms) for case in corpus.cases) * corpus.repeats == 24
    groups: dict[str, list] = {}
    for case in corpus.cases:
        groups.setdefault(str(case.comparison_group), []).append(case)
    assert len(groups) == 6
    for cases in groups.values():
        assert {case.variant_id for case in cases} == {
            "repair_disabled", "repair_enabled",
        }
        assert len({
            (case.item_count, case.container_count, case.item_selection_strategy,
             case.item_selection_seed)
            for case in cases
        }) == 1


def test_level3_repair_ab_corpus_is_bounded_fair_and_complete(root: Path) -> None:
    corpus = load_benchmark_corpus(
        root / "config/level_03/benchmarks/repair_ab_100_500_manual.yaml",
        project_root=root,
    )
    assert corpus.level_id == "level_03"
    assert len(corpus.cases) == 12
    assert corpus.repeats == 2
    assert sum(len(case.algorithms) for case in corpus.cases) * corpus.repeats == 72
    groups: dict[str, list] = {}
    for case in corpus.cases:
        groups.setdefault(str(case.comparison_group), []).append(case)
        assert set(case.algorithms) == {
            "extreme_point_best_fit", "extreme_point_ffd", "maximal_space_best_fit",
        }
    assert len(groups) == 6
    expected_limits = {100: (3, 7, 60, 20), 300: (9, 18, 120, 45), 500: (14, 28, 180, 60)}
    for cases in groups.values():
        assert {case.variant_id for case in cases} == {
            "repair_disabled", "repair_enabled",
        }
        assert len({
            (case.item_count, case.container_count, case.item_selection_strategy,
             case.item_selection_seed)
            for case in cases
        }) == 1
        for case in cases:
            search = case.config_overrides["container_search"]
            start, maximum, deadline, repair_budget = expected_limits[case.item_count]
            assert search["initial_used_container_count"] == start
            assert search["max_used_container_count"] == maximum
            assert search["time_limit_seconds"] == deadline
            assert search["validation_reserve_seconds"] == 3
            consolidation = search["consolidation"]
            if case.variant_id == "repair_enabled":
                assert consolidation["enabled"] is True
                assert consolidation["time_limit_seconds"] == repair_budget
                assert consolidation["container_elimination"]["enabled"] is True
            else:
                assert consolidation["enabled"] is False
                assert consolidation["container_elimination"]["enabled"] is False


def test_level1_gap_fill_generated_scale_gates_use_one_qualified_fixed_fleet(
    root: Path,
) -> None:
    config_path = (
        root
        / "config/level_01/experiments/ep_ffd_gap_fill_generated_1k_fixed_fleet_local.yaml"
    )
    config = load_config(config_path)
    generated_root = Path("data/interim/synthetic/empirical_scale_1k_100_v1")
    manifest_path = root / generated_root / "generation_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    usage = validate_dataset_usage(
        root, config, DatasetExecutionIntent.BENCHMARK_ACCEPTANCE,
    )

    assert config["paths"]["raw_items_csv"] == str(generated_root / "solver_items.csv").replace("\\", "/")
    assert config["paths"]["raw_containers_csv"] == str(generated_root / "solver_containers.csv").replace("\\", "/")
    assert config["paths"]["items_source_mapping"] == "config/common/data_sources/empirical_template_level_08.yaml"
    assert config["paths"]["processed_dir"] == "data/processed/level_01/gap_fill_generated_1k"
    assert config["dataset_policy"] == {
        "generation_manifest": str(generated_root / "generation_manifest.json").replace("\\", "/"),
        "expected_usage_class": "solver_research",
    }
    assert config["instance"]["container_count"] == 100
    assert config["container_search"]["enabled"] is False
    assert config["algorithms"]["extreme_point_ffd"]["fixed_subset"] is True
    assert config["algorithms"]["extreme_point_ffd_gap_fill"]["fixed_subset"] is True
    assert config["algorithms"]["extreme_point_ffd_gap_fill"]["gap_fill"] == {
        "lookahead_window_size": 5,
        "max_constrained_points_per_step": 8,
        "max_candidates_per_step": 64,
        "maximum_reorder_distance": 4,
    }
    assert manifest["item_count"] == 1000
    assert manifest["container_count"] == 100
    assert manifest["usage_class"] == "solver_research"
    assert manifest["capacity_qualification"] == "solver_qualified"
    assert manifest["solver_acceptance_allowed"] is True
    assert usage is not None
    assert usage.profile_id == "empirical_scale_1k_100_v1"
    assert usage.solver_acceptance_allowed is True
    assert usage.execution_intent == "benchmark_acceptance"
    for key in ("raw_items_csv", "raw_containers_csv", "processed_dir", "manifest_json"):
        configured_path = Path(config["paths"][key])
        assert not configured_path.is_absolute()
        assert "outputs" not in configured_path.parts

    suite_specs = (
        ("ep_ffd_gap_fill_generated_1k_gate_a_i100_manual.yaml", 100, (None, 101, 202, 303), 8),
        ("ep_ffd_gap_fill_generated_1k_gate_b_i300_manual.yaml", 300, (None, 101, 202, 303), 8),
        ("ep_ffd_gap_fill_generated_1k_gate_c_i500_manual.yaml", 500, (None, 101), 4),
    )
    expected_algorithms = ("extreme_point_ffd", "extreme_point_ffd_gap_fill")
    for filename, item_count, selection_seeds, source_run_count in suite_specs:
        suite = load_benchmark_suite(root / "config/level_01/benchmarks" / filename)
        assert suite.config_path == Path(
            "config/level_01/experiments/ep_ffd_gap_fill_generated_1k_fixed_fleet_local.yaml"
        )
        assert suite.algorithms == expected_algorithms
        assert suite.seeds == (42,)
        assert suite.repeats == 1
        assert len(suite.scenarios) * len(suite.algorithms) == source_run_count
        assert [value.item_selection_seed for value in suite.scenarios] == list(selection_seeds)
        assert all(value.item_count == item_count for value in suite.scenarios)
        assert all(value.container_count == 100 for value in suite.scenarios)
        assert all(value.algorithm_ids == expected_algorithms for value in suite.scenarios)
        assert all("fixed_fleet" in value.tags for value in suite.scenarios)
        assert not suite.config_path.is_absolute()
        assert "outputs" not in suite.config_path.parts


def test_level1_inventory_scale_gate_suites_are_bounded_and_reproducible(
    root: Path,
) -> None:
    specifications = (
        (
            "config/level_01/experiments/extreme_point_best_fit_inventory_fleet_500.yaml",
            "config/level_01/benchmarks/inventory_fleet_500_manual.yaml",
            500,
            10,
            "level_01_inventory_fleet_500_t10_v1",
            ((20, 1), (50, 1)),
            8,
            30,
        ),
        (
            "config/level_01/experiments/extreme_point_best_fit_inventory_fleet_5000.yaml",
            "config/level_01/benchmarks/inventory_fleet_5000_manual.yaml",
            5_000,
            25,
            "level_01_inventory_fleet_5000_t25_v1",
            ((100, 1),),
            4,
            60,
        ),
    )
    algorithms = ("extreme_point_best_fit", "extreme_point_ffd")

    for (
        config_name,
        suite_name,
        physical_count,
        type_count,
        expected_profile_id,
        expected_scenarios,
        expected_source_runs,
        expected_seconds,
    ) in specifications:
        config = load_config(root / config_name)
        suite = load_benchmark_suite(root / suite_name)
        usage = validate_dataset_usage(
            root, config, DatasetExecutionIntent.BENCHMARK_ACCEPTANCE,
        )
        manifest_path = root / config["dataset_policy"]["generation_manifest"]
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        assert usage is not None
        assert usage.solver_acceptance_allowed is True
        assert usage.profile_id == expected_profile_id
        assert manifest["container_count"] == physical_count
        assert len(manifest["container_type_quantities"]) == type_count
        assert manifest["solver_acceptance_allowed"] is True
        assert config["container_search"]["enabled"] is True
        assert config["container_search"]["time_limit_seconds"] == expected_seconds
        assert config["container_search"]["max_candidates_per_count"] < physical_count
        assert config["container_search"]["exhaustive_max_containers"] <= 10
        assert suite.algorithms == algorithms
        assert suite.seeds == (42,)
        assert suite.repeats == 2
        assert tuple((value.item_count, value.container_count) for value in suite.scenarios) == expected_scenarios
        assert len(suite.scenarios) * len(suite.algorithms) * suite.repeats == expected_source_runs
        assert all(value.container_count == 1 for value in suite.scenarios)
        assert all("inventory_gate" in value.tags for value in suite.scenarios)
        assert not suite.config_path.is_absolute()


def test_level8_sequential_scale_suites_sample_from_source_1000(
    root: Path,
) -> None:
    source_config = (
        "config/level_08/experiments/"
        "synthetic_delivery_1000_sequential_local.yaml"
    )
    suite_100 = load_benchmark_suite(
        root / "config/level_08/benchmarks/sequential_replay_100_manual.yaml"
    )
    suite_300 = load_benchmark_suite(
        root / "config/level_08/benchmarks/sequential_replay_300_manual.yaml"
    )
    config = load_config(root / source_config)

    assert suite_100.config_path == Path(source_config)
    assert suite_300.config_path == Path(source_config)
    assert config["paths"]["raw_items_csv"].endswith(
        "level_08_scale_1000_c80_items.csv"
    )
    assert config["sequential_simulation"]["enabled"] is True
    assert config["sequential_balance_construction_enabled"] is True
    assert [(value.item_count, value.container_count) for value in suite_100.scenarios] == [
        (100, 10),
        (100, 10),
    ]
    assert [
        (value.item_selection_strategy, value.item_selection_seed)
        for value in suite_300.scenarios
    ] == [
        ("prefix", None),
        ("stable_random", 101),
        ("stable_random", 202),
        ("stable_random", 303),
    ]


def test_benchmark_creates_isolated_aggregate_and_source_runs(root: Path, tmp_path: Path):
    config = load_config(root / "config/level_01/default.yaml")
    config["paths"]["raw_items_csv"] = str(root / "data/raw/dataset_small_items_original.csv")
    config["paths"]["processed_dir"] = str(tmp_path / "processed/level_01")
    config["paths"]["manifest_json"] = str(tmp_path / "processed/level_01/latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / "outputs")
    config_path = tmp_path / "level_01.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    result = run_benchmark(
        level_id="level_01", algorithm_ids=[
            "milp_big_m", "extreme_point_best_fit", "extreme_point_ffd", "extreme_point_hill_climbing",
            "extreme_point_simulated_annealing", "maximal_space_best_fit",
        ], item_counts=[1],
        container_counts=[2], repeats=1, config_path=config_path, project_root=root,
    )

    assert result.successful
    assert "__level_01__benchmark__" in result.benchmark_id
    assert result.run_dir.parent.name == "runs"
    assert (result.run_dir / "benchmark/results.csv").is_file()
    assert (result.run_dir / "benchmark/summary.csv").is_file()
    assert (result.run_dir / "benchmark/ranking.csv").is_file()
    assert (result.run_dir / "benchmark/pairwise_comparison.csv").is_file()
    assert (result.run_dir / "benchmark/pareto_frontier.csv").is_file()
    assert (result.run_dir / "benchmark/milp_reference_gaps.csv").is_file()
    assert (result.run_dir / "logs/run.log").is_file()
    manifest = json.loads((result.run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_type"] == "benchmark"
    assert manifest["case_count"] == 6
    assert manifest["successful_case_count"] == 6
    assert len(manifest["source_runs"]) == 6
    assert len(set(result.results["experiment_run_id"])) == 6
    assert set(result.summary["algorithm"]) == {
        "milp_big_m", "extreme_point_best_fit", "extreme_point_ffd", "extreme_point_hill_climbing",
        "extreme_point_simulated_annealing", "maximal_space_best_fit",
    }
    assert set(result.summary["run_count"]) == {1}
    assert set(result.summary["seed_count"]) == {1}
    assert set(result.results["random_seed"]) == {42}
    assert manifest["random_seeds"] == [42]
    assert result.analysis.ranking["is_lexicographic_winner"].sum() == 1


def test_multi_seed_sweep_tracks_seed_repeats_and_resolved_configs(root: Path, tmp_path: Path):
    config = load_config(root / "config/level_01/default.yaml")
    config["paths"]["raw_items_csv"] = str(root / "data/raw/dataset_small_items_original.csv")
    config["paths"]["processed_dir"] = str(tmp_path / "processed/level_01")
    config["paths"]["manifest_json"] = str(tmp_path / "processed/level_01/latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / "outputs")
    config_path = tmp_path / "level_01.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    result = run_benchmark(
        level_id="level_01", algorithm_ids=["extreme_point_simulated_annealing"],
        item_counts=[10], container_counts=[3], seeds=[7, 11, 19], repeats=2,
        config_path=config_path, project_root=root,
    )

    assert result.successful
    assert "__seeds3_" in result.benchmark_id
    assert len(result.results) == 6
    assert set(result.results["random_seed"]) == {7, 11, 19}
    assert set(result.results["repeat"]) == {1, 2}
    assert result.summary.iloc[0].run_count == 6
    assert result.summary.iloc[0].seed_count == 3
    assert result.summary.iloc[0].repeats_per_seed == 2
    assert 1 <= result.summary.iloc[0].distinct_solution_count <= 3
    assert result.results.groupby("random_seed")["placement_signature"].nunique().eq(1).all()

    manifest = json.loads((result.run_dir / "manifest.json").read_text(encoding="utf-8"))
    request = json.loads((result.run_dir / "benchmark/request.json").read_text(encoding="utf-8"))
    assert manifest["random_seed"] is None
    assert manifest["random_seeds"] == [7, 11, 19]
    assert manifest["repeats_per_seed"] == 2
    assert request["random_seeds"] == [7, 11, 19]
    for row in result.results.itertuples():
        run_config = yaml.safe_load((Path(row.experiment_run_dir) / "resolved_config.yaml").read_text(encoding="utf-8"))
        assert run_config["project"]["random_seed"] == row.random_seed
        assert f"__seed{row.random_seed}" in row.experiment_run_id


@pytest.mark.parametrize("seeds", [[], [-1], [7, 7]])
def test_rejects_invalid_seed_sweeps(root: Path, tmp_path: Path, seeds):
    with pytest.raises(ValueError, match="seeds"):
        run_benchmark(
            level_id="level_01", algorithm_ids=["extreme_point_ffd"],
            item_counts=[1], container_counts=[1], seeds=seeds,
            config_path=root / "config/level_01/default.yaml", project_root=root,
        )


def test_quality_standard_deviation_is_computed_across_seeds_not_repeats():
    import pandas as pd

    rows = []
    for seed, objective in ((7, 10.0), (11, 20.0)):
        for repeat, runtime in ((1, 1.0), (2, 2.0)):
            rows.append({
                "level": "level_01", "algorithm": "example", "item_count": 1,
                "container_count": 1, "random_seed": seed, "repeat": repeat,
                "success": True, "status": "FEASIBLE", "algorithm_runtime_seconds": runtime,
                "wall_runtime_seconds": runtime, "objective_value": objective,
                "official_objective": {
                    "used_container_count": 1,
                    "total_container_cost": objective,
                },
                "used_container_count": 1.0, "total_container_cost": objective,
                "occupied_bounding_volume_mm3": objective, "coordinate_compactness_mm": objective,
                "placement_signature": f"{seed}",
            })
    summary = _aggregate(pd.DataFrame(rows)).iloc[0]
    assert summary.objective_mean == 15.0
    assert summary.objective_std == pytest.approx(7.0710678118654755)
    assert summary.run_count == 4
    assert summary.seed_count == 2
    assert summary.repeats_per_seed == 2


def test_named_suite_config_declares_a_level_specific_fair_protocol(root: Path):
    suite = load_benchmark_suite(root / "config/level_01/benchmarks/core_local.yaml")

    assert suite.level_id == "level_01"
    assert suite.suite_id == "level_01_core_local_v2"
    assert [value.scenario_id for value in suite.scenarios] == [
        "small_random_i10_c3", "medium_random_i20_c5", "diverse_volume_i40_c8",
        "payload_heavy_i40_c8", "volume_heavy_i100_c12",
    ]
    assert len(suite.algorithms) == len(set(suite.algorithms))
    assert suite.seeds == (7, 11, 19)
    assert suite.scenarios[0].item_selection_strategy == "stable_random"
    assert suite.scenarios[0].item_selection_seed == 101
    assert "milp_big_m" in suite.scenarios[0].algorithm_ids
    assert all("milp_big_m" not in scenario.algorithm_ids for scenario in suite.scenarios[1:])


def test_level6_constructive_fixture_suite_uses_one_shared_declared_chain(root: Path):
    suite = load_benchmark_suite(
        root / "config/level_06/benchmarks/constructive_chain_fixture_local.yaml"
    )

    assert suite.level_id == "level_06"
    assert suite.algorithms == (
        "extreme_point_ffd_nesting_fixture",
        "extreme_point_best_fit_nesting_fixture",
    )
    assert suite.seeds == (42,)
    assert suite.repeats == 2
    assert [scenario.scenario_id for scenario in suite.scenarios] == ["declared_chain_i3_c1"]


def test_level6_constructive_fixture_benchmark_is_deterministic_and_writes_contract(
    root: Path, tmp_path: Path
):
    suite = load_benchmark_suite(
        root / "config/level_06/benchmarks/constructive_chain_fixture_local.yaml"
    )
    config = load_config(root / suite.config_path)
    config["paths"]["processed_dir"] = str(tmp_path / "processed/level_06")
    config["paths"]["manifest_json"] = str(tmp_path / "processed/level_06/latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / "outputs")
    config_path = tmp_path / "level_06_chain_fixture.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")

    result = run_benchmark(
        level_id=suite.level_id,
        algorithm_ids=suite.algorithms,
        item_counts=[3],
        container_counts=[1],
        repeats=suite.repeats,
        seeds=suite.seeds,
        config_path=config_path,
        project_root=root,
        scenarios=suite.scenarios,
        suite_id=suite.suite_id,
    )

    assert result.successful
    assert len(result.results) == 4
    assert result.results["input_fingerprint"].nunique() == 1
    assert result.results.groupby("algorithm")["placement_signature"].nunique().eq(1).all()
    assert set(result.summary["algorithm"]) == set(suite.algorithms)
    for run_dir in result.results["experiment_run_dir"]:
        path = Path(run_dir)
        assert (path / "solution/nesting_relations.csv").is_file()
        assert (path / "solution/nesting_compounds.csv").is_file()
        assert (path / "validation/compound_geometry_validation.json").is_file()


def test_level2_suite_separates_exact_reference_and_heuristic_scale(root: Path):
    suite = load_benchmark_suite(root / "config/level_02/benchmarks/core_local.yaml")
    assert suite.level_id == "level_02"
    assert suite.suite_id == "level_02_core_local_v1"
    assert [value.scenario_id for value in suite.scenarios] == [
        "exact_reference_i3_c2", "practical_i20_c5", "heuristic_scale_i50_c5",
    ]
    assert "milp_big_m" in suite.scenarios[0].algorithm_ids
    assert "milp_big_m" in suite.scenarios[1].algorithm_ids
    assert "milp_big_m" not in suite.scenarios[2].algorithm_ids


def test_level2_ffd_promotion_suite_declares_profile_matrix_and_repeats(root: Path):
    suite = load_benchmark_suite(root / "config/level_02/benchmarks/ffd_baseline_local.yaml")
    assert suite.level_id == "level_02"
    assert suite.suite_id == "level_02_ffd_baseline_local_v1"
    assert suite.seeds == (42,)
    assert suite.repeats == 3
    assert len(suite.scenarios) == 9
    assert suite.scenarios[0].algorithm_ids == ("extreme_point_ffd", "milp_big_m")
    assert all(
        scenario.algorithm_ids == ("extreme_point_ffd",)
        for scenario in suite.scenarios[1:]
    )
    assert {scenario.item_selection_strategy for scenario in suite.scenarios} == {
        "prefix", "stable_random", "volume_stratified", "largest_volume", "heaviest",
    }


def test_level3_ffd_baseline_suite_declares_deterministic_orientation_protocol(root: Path):
    suite = load_benchmark_suite(root / "config/level_03/benchmarks/ffd_baseline_local.yaml")

    assert suite.level_id == "level_03"
    assert suite.suite_id == "level_03_ffd_baseline_local_v1"
    assert suite.algorithms == ("extreme_point_ffd",)
    assert suite.seeds == (42,)
    assert suite.repeats == 3
    assert [scenario.scenario_id for scenario in suite.scenarios] == [
        "sanity_prefix_i3_c2", "practical_prefix_i20_c5", "stable_random_101_i20_c5",
        "diverse_volume_i40_c8", "scale_prefix_i100_c12",
    ]


def test_level4_ffd_baseline_suite_declares_stackability_protocol(root: Path):
    suite = load_benchmark_suite(root / "config/level_04/benchmarks/ffd_baseline_local.yaml")

    assert suite.level_id == "level_04"
    assert suite.suite_id == "level_04_ffd_baseline_local_v1"
    assert suite.algorithms == ("extreme_point_ffd",)
    assert suite.seeds == (42,)
    assert suite.repeats == 3
    assert [scenario.scenario_id for scenario in suite.scenarios] == [
        "sanity_prefix_i3_c2", "practical_prefix_i10_c3", "practical_prefix_i20_c5",
        "stable_random_101_i20_c5", "diverse_volume_i40_c8", "scale_prefix_i100_c12",
    ]
    assert suite.scenarios[3].item_selection_strategy == "stable_random"
    assert suite.scenarios[3].item_selection_seed == 101


def test_level4_best_fit_baseline_suite_declares_practical_default_protocol(root: Path):
    suite = load_benchmark_suite(root / "config/level_04/benchmarks/best_fit_baseline_local.yaml")

    assert suite.level_id == "level_04"
    assert suite.suite_id == "level_04_best_fit_baseline_local_v1"
    assert suite.algorithms == ("extreme_point_best_fit",)
    assert suite.seeds == (42,)
    assert suite.repeats == 3
    assert len(suite.scenarios) == 6
    assert all(scenario.algorithm_ids == suite.algorithms for scenario in suite.scenarios)


def test_level4_core_constructive_suite_uses_shared_stackability_inputs(root: Path):
    suite = load_benchmark_suite(root / "config/level_04/benchmarks/core_constructive_local.yaml")

    assert suite.level_id == "level_04"
    assert suite.suite_id == "level_04_core_constructive_local_v1"
    assert suite.algorithms == (
        "extreme_point_ffd", "extreme_point_best_fit", "maximal_space_best_fit",
    )
    assert suite.repeats == 3
    assert all(scenario.algorithm_ids == suite.algorithms for scenario in suite.scenarios)
    assert suite.scenarios[-1].item_selection_strategy == "volume_stratified"


def test_level4_local_search_suite_compares_best_fit_with_hill_climbing(root: Path):
    suite = load_benchmark_suite(root / "config/level_04/benchmarks/local_search_local.yaml")

    assert suite.level_id == "level_04"
    assert suite.suite_id == "level_04_local_search_local_v1"
    assert suite.algorithms == ("extreme_point_best_fit", "extreme_point_hill_climbing")
    assert suite.repeats == 3
    assert all(scenario.algorithm_ids == suite.algorithms for scenario in suite.scenarios)


def test_level4_metaheuristic_suite_uses_shared_seeded_inputs(root: Path):
    suite = load_benchmark_suite(root / "config/level_04/benchmarks/metaheuristic_local.yaml")

    assert suite.level_id == "level_04"
    assert suite.suite_id == "level_04_metaheuristic_local_v1"
    assert suite.algorithms == (
        "extreme_point_best_fit", "extreme_point_hill_climbing",
        "extreme_point_simulated_annealing",
    )
    assert suite.seeds == (42,)
    assert all(scenario.algorithm_ids == suite.algorithms for scenario in suite.scenarios)


def test_level4_portfolio_suite_declares_common_profiles_and_seed_sweep(root: Path):
    suite = load_benchmark_suite(root / "config/level_04/benchmarks/portfolio_local.yaml")

    assert suite.level_id == "level_04"
    assert suite.suite_id == "level_04_solver_portfolio_local_v1"
    assert suite.algorithms == (
        "extreme_point_best_fit", "extreme_point_hill_climbing",
        "extreme_point_simulated_annealing",
    )
    assert suite.seeds == (7, 11, 19)
    assert suite.repeats == 1
    assert [scenario.scenario_id for scenario in suite.scenarios] == [
        "portfolio_prefix_i20_c5", "portfolio_stable_random_101_i20_c5",
    ]
    assert suite.scenarios[1].item_selection_strategy == "stable_random"
    assert suite.scenarios[1].item_selection_seed == 101


def test_level5_constructive_suite_compares_shared_load_bearing_inputs(
    root: Path,
):
    suite = load_benchmark_suite(
        root / "config/level_05/benchmarks/constructive_local.yaml"
    )

    assert suite.level_id == "level_05"
    assert suite.suite_id == "level_05_constructive_local_v1"
    assert suite.algorithms == ("extreme_point_best_fit", "extreme_point_ffd")
    assert suite.seeds == (42,)
    assert suite.repeats == 3
    assert all(
        scenario.algorithm_ids == suite.algorithms for scenario in suite.scenarios
    )


def test_level5_local_search_suite_compares_best_fit_with_hill_climbing(
    root: Path,
):
    suite = load_benchmark_suite(
        root / "config/level_05/benchmarks/local_search_local.yaml"
    )

    assert suite.level_id == "level_05"
    assert suite.suite_id == "level_05_local_search_local_v1"
    assert suite.algorithms == (
        "extreme_point_best_fit", "extreme_point_hill_climbing",
    )
    assert suite.seeds == (42,)
    assert suite.repeats == 3


def test_level5_metaheuristic_suite_uses_shared_seeded_inputs(root: Path):
    suite = load_benchmark_suite(
        root / "config/level_05/benchmarks/metaheuristic_local.yaml"
    )

    assert suite.level_id == "level_05"
    assert suite.suite_id == "level_05_metaheuristic_local_v1"
    assert suite.algorithms == (
        "extreme_point_best_fit", "extreme_point_hill_climbing",
        "extreme_point_simulated_annealing",
    )
    assert suite.seeds == (42,)
    assert suite.repeats == 3
    assert suite.scenarios[-1].item_selection_strategy == "stable_random"
    assert suite.scenarios[-1].item_selection_seed == 101


def test_level5_portfolio_suite_declares_common_profiles_and_seed_sweep(root: Path):
    suite = load_benchmark_suite(
        root / "config/level_05/benchmarks/portfolio_local.yaml"
    )

    assert suite.level_id == "level_05"
    assert suite.suite_id == "level_05_solver_portfolio_local_v1"
    assert suite.algorithms == (
        "extreme_point_best_fit", "extreme_point_hill_climbing",
        "extreme_point_simulated_annealing",
    )
    assert suite.seeds == (7, 11, 19)
    assert suite.repeats == 1
    assert [scenario.scenario_id for scenario in suite.scenarios] == [
        "portfolio_prefix_i20_c5", "portfolio_stable_random_101_i20_c5",
    ]
    assert suite.scenarios[1].item_selection_strategy == "stable_random"
    assert suite.scenarios[1].item_selection_seed == 101


def test_level7_acceptance_suites_separate_primary_and_comparator(root: Path):
    primary = load_benchmark_suite(
        root / "config/level_07/benchmarks/primary_best_fit_acceptance_local.yaml"
    )
    comparator = load_benchmark_suite(
        root / "config/level_07/benchmarks/ffd_comparator_local.yaml"
    )

    assert primary.algorithms == ("extreme_point_best_fit_balance",)
    assert primary.repeats == 2
    assert comparator.algorithms == ("extreme_point_ffd_balance",)
    assert comparator.repeats == 1
    assert [value.scenario_id for value in primary.scenarios] == [
        value.scenario_id for value in comparator.scenarios
    ]
    assert len(primary.scenarios) == 6
    assert [value.item_selection_seed for value in primary.scenarios[-3:]] == [
        101, 202, 303,
    ]


def test_level4_portfolio_algorithms_share_one_frozen_input(root: Path, tmp_path: Path):
    config = load_config(root / "config/level_04/default.yaml")
    config["paths"].update({
        "raw_items_csv": str(root / "data/raw/dataset_small_items_original.csv"),
        "processed_dir": str(tmp_path / "processed" / "level_04"),
        "manifest_json": str(tmp_path / "processed" / "level_04" / "latest_manifest.json"),
        "output_root": str(tmp_path / "outputs"),
    })
    config_path = tmp_path / "level_04.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    algorithms = (
        "extreme_point_best_fit", "extreme_point_hill_climbing",
        "extreme_point_simulated_annealing",
    )
    scenario = BenchmarkScenario(
        "portfolio_fixture", "Tiny shared Level 4 profile", 1, 2,
        algorithm_ids=algorithms, item_selection_strategy="stable_random", item_selection_seed=101,
    )

    result = run_benchmark(
        level_id="level_04", algorithm_ids=algorithms, item_counts=[1], container_counts=[2],
        seeds=[7], repeats=1, config_path=config_path, project_root=root,
        scenarios=[scenario], suite_id="level_04_portfolio_fixture",
    )

    assert result.successful
    assert set(result.results["algorithm"]) == set(algorithms)
    assert result.results["input_fingerprint"].nunique() == 1
    assert result.results["selected_item_ids_checksum"].nunique() == 1
    assert set(result.results["item_selection_strategy"]) == {"stable_random"}


def test_level3_core_heuristic_suite_compares_only_shared_level3_inputs(root: Path):
    suite = load_benchmark_suite(root / "config/level_03/benchmarks/core_heuristics_local.yaml")

    assert suite.level_id == "level_03"
    assert suite.suite_id == "level_03_core_heuristics_local_v1"
    assert suite.algorithms == (
        "extreme_point_ffd", "extreme_point_best_fit", "extreme_point_hill_climbing",
        "extreme_point_simulated_annealing", "maximal_space_best_fit",
    )
    assert suite.repeats == 3
    assert suite.scenarios[0].algorithm_ids == suite.algorithms
    assert suite.scenarios[-1].algorithm_ids == (
        "extreme_point_ffd", "extreme_point_best_fit", "maximal_space_best_fit",
    )


def test_level3_ffd_repeats_persist_horizontal_orientation_profile(root: Path, tmp_path: Path):
    config = load_config(root / "config/level_03/default.yaml")
    config["paths"].update({
        "raw_items_csv": str(root / "data/raw/dataset_small_items_original.csv"),
        "processed_dir": str(tmp_path / "processed/level_03"),
        "manifest_json": str(tmp_path / "processed/level_03/latest_manifest.json"),
        "output_root": str(tmp_path / "outputs"),
    })
    config_path = tmp_path / "level_03.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    scenario = BenchmarkScenario(
        "orientation_determinism", "Repeated horizontal-orientation FFD", 3, 2,
        algorithm_ids=("extreme_point_ffd",),
    )
    result = run_benchmark(
        level_id="level_03", algorithm_ids=["extreme_point_ffd"],
        item_counts=[3], container_counts=[2], seeds=[42], repeats=3,
        config_path=config_path, project_root=root, scenarios=[scenario],
        suite_id="orientation_determinism_test",
    )

    assert result.successful
    assert result.results["placement_signature"].nunique() == 1
    assert result.results["objective_value"].nunique() == 1
    assert set(result.results["orientation_profile"]) == {"horizontal_rotatable"}
    assert set(result.results["feasibility_policy"]) == {
        "horizontal_orientation_geometry_payload_exact_support",
    }
    assert result.results["orientation_candidates_evaluated"].min() >= 3


def test_level2_ffd_repeats_are_deterministic_on_same_input(root: Path, tmp_path: Path):
    config = load_config(root / "config/level_02/default.yaml")
    config["paths"]["raw_items_csv"] = str(root / "data/raw/dataset_small_items_original.csv")
    config["paths"]["processed_dir"] = str(tmp_path / "processed/level_02")
    config["paths"]["manifest_json"] = str(tmp_path / "processed/level_02/latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / "outputs")
    config_path = tmp_path / "level_02.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    scenario = BenchmarkScenario(
        "ffd_determinism", "Repeated deterministic Level 2 FFD", 3, 2,
        algorithm_ids=("extreme_point_ffd",),
    )
    result = run_benchmark(
        level_id="level_02", algorithm_ids=["extreme_point_ffd"],
        item_counts=[3], container_counts=[2], seeds=[42], repeats=3,
        config_path=config_path, project_root=root, scenarios=[scenario],
        suite_id="ffd_determinism_test",
    )
    assert result.successful
    assert result.results["placement_signature"].nunique() == 1
    assert result.results["objective_value"].nunique() == 1
    assert set(result.results["feasibility_policy"]) == {
        "fixed_orientation_geometry_payload_exact_support",
    }
    assert result.results["minimum_exact_support_ratio"].min() >= 0.8


def test_scenario_rows_share_one_input_fingerprint_across_algorithms(root: Path, tmp_path: Path):
    config = load_config(root / "config/level_01/default.yaml")
    config["paths"]["raw_items_csv"] = str(root / "data/raw/dataset_small_items_original.csv")
    config["paths"]["processed_dir"] = str(tmp_path / "processed/level_01")
    config["paths"]["manifest_json"] = str(tmp_path / "processed/level_01/latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / "outputs")
    config_path = tmp_path / "level_01.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    scenario = BenchmarkScenario(
        scenario_id="fair_mini", description="One shared mini instance", item_count=1, container_count=2,
        tags=("test", "small"), item_selection_strategy="stable_random", item_selection_seed=101,
    )

    result = run_benchmark(
        level_id="level_01", algorithm_ids=["extreme_point_ffd", "extreme_point_best_fit"],
        item_counts=[1], container_counts=[2], seeds=[7, 11], config_path=config_path,
        project_root=root, scenarios=[scenario], suite_id="test_fair_suite",
    )

    assert result.successful
    assert set(result.results["scenario_id"]) == {"fair_mini"}
    assert result.results["input_fingerprint"].nunique() == 1
    assert result.results["selected_item_ids_checksum"].nunique() == 1
    assert set(result.results["item_selection_strategy"]) == {"stable_random"}
    assert set(result.summary["suite_id"]) == {"test_fair_suite"}
    assert result.summary.groupby("scenario_id")["input_fingerprint"].nunique().eq(1).all()
    snapshots = [
        pd.read_csv(Path(run_dir) / "input_snapshot/items.csv")["id_item"].tolist()
        for run_dir in result.results["experiment_run_dir"]
    ]
    assert all(value == snapshots[0] for value in snapshots)
    for run_dir in result.results["experiment_run_dir"]:
        source_manifest = json.loads((Path(run_dir) / "manifest.json").read_text(encoding="utf-8"))
        source_config = yaml.safe_load((Path(run_dir) / "resolved_config.yaml").read_text(encoding="utf-8"))
        assert source_manifest["item_selection"]["strategy"] == "stable_random"
        assert source_manifest["item_selection"]["seed"] == 101
        assert source_config["instance"]["item_selection_strategy"] == "stable_random"
        assert source_config["instance"]["item_selection_seed"] == 101


def test_scenario_algorithm_policy_restricts_milp_to_reference_case(root: Path, tmp_path: Path):
    config = load_config(root / "config/level_01/default.yaml")
    config["paths"]["raw_items_csv"] = str(root / "data/raw/dataset_small_items_original.csv")
    config["paths"]["processed_dir"] = str(tmp_path / "processed/level_01")
    config["paths"]["manifest_json"] = str(tmp_path / "processed/level_01/latest_manifest.json")
    config["paths"]["output_root"] = str(tmp_path / "outputs")
    config_path = tmp_path / "level_01.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    scenarios = [
        BenchmarkScenario(
            "reference", "Exact reference", 1, 2,
            algorithm_ids=("milp_big_m", "extreme_point_ffd"),
        ),
        BenchmarkScenario(
            "scale", "Heuristic-only scale case", 2, 2,
            algorithm_ids=("extreme_point_ffd",), item_selection_strategy="heaviest",
        ),
    ]

    result = run_benchmark(
        level_id="level_01", algorithm_ids=["milp_big_m", "extreme_point_ffd"],
        item_counts=[1], container_counts=[2], seeds=[7], config_path=config_path,
        project_root=root, scenarios=scenarios, suite_id="policy_test",
    )

    assert result.successful
    assert len(result.results) == 3
    assert set(result.results.loc[result.results.algorithm == "milp_big_m", "scenario_id"]) == {"reference"}
    assert set(result.results.loc[result.results.scenario_id == "scale", "algorithm"]) == {"extreme_point_ffd"}
    request = json.loads((result.run_dir / "benchmark/request.json").read_text(encoding="utf-8"))
    policies = {value["scenario_id"]: value["algorithms"] for value in request["scenarios"]}
    assert policies == {
        "reference": ["milp_big_m", "extreme_point_ffd"],
        "scale": ["extreme_point_ffd"],
    }


@pytest.mark.parametrize("level_id", ["level_04", "level_05"])
def test_contact_support_index_ab_corpus_is_paired_and_complete(
    root: Path, level_id: str,
) -> None:
    corpus = load_benchmark_corpus(
        root / f"config/{level_id}/benchmarks/contact_support_index_ab_manual.yaml",
        project_root=root,
    )

    assert corpus.execution_schedule == "paired_alternating"
    assert len(corpus.cases) == 12
    assert sum(len(case.algorithms) for case in corpus.cases) * corpus.repeats == 108
    groups: dict[str, list] = {}
    for case in corpus.cases:
        groups.setdefault(str(case.comparison_group), []).append(case)
        assert case.config_overrides["container_search"]["consolidation"]["enabled"] is False
    assert len(groups) == 6
    for cases in groups.values():
        assert {case.variant_id for case in cases} == {
            "contact_index_disabled", "contact_index_enabled",
        }
        assert len({case.item_count for case in cases}) == 1
        assert len({case.item_selection_strategy for case in cases}) == 1
        assert len({case.item_selection_seed for case in cases}) == 1


@pytest.mark.parametrize("level_id", ["level_04", "level_05"])
def test_contact_support_index_v2_inherits_v1_without_mutating_protocol(
    root: Path, level_id: str,
) -> None:
    v1 = load_benchmark_corpus(
        root / f"config/{level_id}/benchmarks/contact_support_index_ab_manual.yaml",
        project_root=root,
    )
    v2 = load_benchmark_corpus(
        root / f"config/{level_id}/benchmarks/contact_support_index_v2_ab_manual.yaml",
        project_root=root,
    )

    assert v2.corpus_id == f"{level_id}_contact_support_index_ab_v2"
    assert v2.level_id == v1.level_id
    assert v2.execution_schedule == v1.execution_schedule == "paired_alternating"
    assert v2.repeats == v1.repeats == 3
    assert v2.cases == v1.cases
