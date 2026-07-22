import json

import pytest

from container_packing.application.service import (
    build_experiment_request,
    discover_benchmarks,
    discover_runs,
    get_instance_limits,
    load_benchmark_tables,
)


def test_web_application_boundary_builds_registry_validated_request(root):
    config = root / "config/level_01/default.yaml"
    limits = get_instance_limits(config, root=root)
    assert limits.available_items == 501
    assert limits.configured_containers == 5
    request = build_experiment_request(
        level_id="level_01", algorithm_id="extreme_point_ffd",
        item_count=30, container_count=7, random_seed=11,
        config_path=config, root=root,
    )
    assert request.item_count == 30
    assert request.container_count == 7
    assert request.random_seed == 11


def test_application_boundary_rejects_unavailable_item_count(root):
    with pytest.raises(ValueError, match="only 501"):
        build_experiment_request(
            level_id="level_01", algorithm_id="extreme_point_ffd",
            item_count=502, container_count=5,
            config_path=root / "config/level_01/default.yaml", root=root,
        )


def test_run_discovery_is_level_isolated(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    (tmp_path / "config").mkdir()
    first = tmp_path / "outputs/level_01/runs/run-1"
    first.mkdir(parents=True)
    (first / "metrics").mkdir()
    (first / "manifest.json").write_text(json.dumps({
        "run_id": "run-1", "level": "level_01", "algorithm": "milp_big_m",
        "status": "OPTIMAL", "validation_status": "VALID", "created_at_utc": "2026-01-01T00:00:00Z",
    }), encoding="utf-8")
    (first / "metrics/metrics.json").write_text(json.dumps({
        "n_items": 10, "n_containers_available": 3,
    }), encoding="utf-8")
    other = tmp_path / "outputs/level_02/runs/run-2"
    other.mkdir(parents=True)
    (other / "manifest.json").write_text("{}", encoding="utf-8")
    runs = discover_runs("level_01", root=tmp_path)
    assert len(runs) == 1
    assert runs[0].run_id == "run-1"
    assert runs[0].item_count == 10


def test_benchmark_discovery_and_table_loading_are_separate_from_run_history(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='fixture'\n", encoding="utf-8")
    (tmp_path / "config").mkdir()
    run_dir = tmp_path / "outputs/level_01/runs/corpus-1"
    benchmark_dir = run_dir / "benchmark"
    benchmark_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text(json.dumps({
        "run_id": "corpus-1", "run_type": "benchmark_corpus", "level": "level_01",
        "status": "SUCCESS", "created_at_utc": "2026-01-01T00:00:00Z",
        "corpus_id": "fixture", "case_count": 2, "execution_count": 4,
    }), encoding="utf-8")
    for name in ("results.csv", "summary.csv"):
        (benchmark_dir / name).write_text("case_id,algorithm\ncase-a,example\n", encoding="utf-8")
    (benchmark_dir / "ranking.csv").write_text("rank,case_id\n1,case-a\n", encoding="utf-8")
    (benchmark_dir / "references.csv").write_text(
        "case_id,reference_kind\ncase-a,proven_optimal\n", encoding="utf-8",
    )

    assert discover_runs("level_01", root=tmp_path) == ()
    artifacts = discover_benchmarks("level_01", root=tmp_path)
    assert len(artifacts) == 1
    assert artifacts[0].corpus_id == "fixture"
    assert artifacts[0].execution_count == 4
    tables = load_benchmark_tables(run_dir, root=tmp_path)
    assert tables.summary.iloc[0].case_id == "case-a"
    assert tables.ranking.iloc[0]["rank"] == 1
    assert tables.references.iloc[0].reference_kind == "proven_optimal"
