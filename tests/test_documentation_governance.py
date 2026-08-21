from __future__ import annotations

from hashlib import sha256
import json
import re
from pathlib import Path

import yaml

from container_packing.algorithms.registry import get_algorithm, list_algorithms
from container_packing.levels.registry import get_level, list_levels


_EXECUTION_CLASSES = {
    "exact_reference",
    "packing_solver",
    "packing_fixture",
    "validation_fixture",
    "replay_fixture",
}
_MATURITY_CLASSES = {"accepted", "experimental", "fixture_only"}
_LEVEL_MATURITY_CLASSES = {"accepted_research", "experimental"}
_EXPOSURES = {"cli", "benchmark", "streamlit"}
_MOJIBAKE_MARKERS = (
    "\u00c3",
    "\u00c4",
    "\u00e2\u20ac",
    "\u00e1\u00ba",
    "\u00e1\u00bb",
)
_USER_FACING_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".tex"}


def _capability_matrix(root: Path) -> dict:
    path = root / "config/common/capability_matrix.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8-sig"))


def test_capability_matrix_covers_every_registered_binding(root: Path) -> None:
    payload = _capability_matrix(root)
    assert payload["schema_version"] == "1.0"
    matrix_levels = payload["levels"]
    runtime_levels = {level.level_id: level for level in list_levels()}
    assert set(matrix_levels) == set(runtime_levels)

    for level_id, level in runtime_levels.items():
        entry = matrix_levels[level_id]
        assert entry["maturity"] in _LEVEL_MATURITY_CLASSES
        assert set(entry["algorithms"]) == set(level.supported_algorithms)
        assert entry["evidence"]
        for relative_path in entry["evidence"]:
            assert (root / relative_path).is_file(), relative_path

        for algorithm_id, capability in entry["algorithms"].items():
            algorithm = get_algorithm(algorithm_id)
            exposure = set(capability["exposure"])
            assert capability["execution_class"] in _EXECUTION_CLASSES
            assert capability["maturity"] in _MATURITY_CLASSES
            assert isinstance(capability["role"], str) and capability["role"]
            assert exposure <= _EXPOSURES
            assert {"cli", "benchmark"} <= exposure
            assert ("streamlit" in exposure) is (
                level.web_visible and algorithm.web_visible
            )


def test_canonical_documentation_exists_for_every_level(root: Path) -> None:
    index = (root / "docs/index.md").read_text(encoding="utf-8-sig")
    for level in list_levels():
        document = root / f"docs/levels/{level.level_id}.md"
        assert document.is_file()
        assert f"levels/{level.level_id}.md" in index


def test_important_markdown_links_resolve(root: Path) -> None:
    link_pattern = re.compile(r"\[[^]]+\]\(([^)]+)\)")
    for document in (root / "README.md", root / "docs/index.md"):
        text = document.read_text(encoding="utf-8-sig")
        for target in link_pattern.findall(text):
            if target.startswith(("http://", "https://", "#")):
                continue
            clean_target = target.split("#", 1)[0]
            assert (document.parent / clean_target).resolve().is_file(), (
                document,
                target,
            )


def test_user_facing_source_and_docs_do_not_contain_mojibake(root: Path) -> None:
    offenders: list[str] = []
    for base in (root / "src", root / "config", root / "docs"):
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in _USER_FACING_SUFFIXES:
                continue
            text = path.read_text(encoding="utf-8-sig")
            if any(marker in text for marker in _MOJIBAKE_MARKERS):
                offenders.append(str(path.relative_to(root)))
    for path in (root / "README.md", root / "CHANGELOG.md"):
        text = path.read_text(encoding="utf-8-sig")
        if any(marker in text for marker in _MOJIBAKE_MARKERS):
            offenders.append(str(path.relative_to(root)))
    assert offenders == []


def _listed_benchmark_algorithms(value: object) -> set[str]:
    algorithms: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            if key == "algorithms" and isinstance(nested, list):
                algorithms.update(item for item in nested if isinstance(item, str))
            algorithms.update(_listed_benchmark_algorithms(nested))
    elif isinstance(value, list):
        for nested in value:
            algorithms.update(_listed_benchmark_algorithms(nested))
    return algorithms


def test_benchmark_protocols_only_reference_registered_level_algorithms(root: Path) -> None:
    offenders: list[str] = []
    for level in list_levels():
        benchmark_root = root / "config" / level.level_id / "benchmarks"
        if not benchmark_root.is_dir():
            continue
        supported = set(level.supported_algorithms)
        for path in sorted(benchmark_root.glob("*.yaml")):
            payload = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
            unknown = sorted(_listed_benchmark_algorithms(payload) - supported)
            if unknown:
                offenders.append(f"{path.relative_to(root)}: {', '.join(unknown)}")
    assert offenders == []


def test_research_and_web_algorithm_governance_is_consistent() -> None:
    level1_algorithms = {value.algorithm_id: value for value in list_algorithms(level_id="level_01")}
    for algorithm_id in (
        "extreme_point_best_fit_projected_ep",
        "extreme_point_ffd_projected_ep",
    ):
        assert algorithm_id in level1_algorithms
        assert level1_algorithms[algorithm_id].web_visible is False

    level5 = get_level("level_05")
    mes = get_algorithm("maximal_space_best_fit")
    assert "maximal_space_best_fit" in level5.supported_algorithms
    assert "level_05" in mes.supported_levels
    assert mes.web_visible is True

    registered = {value.algorithm_id for value in list_algorithms()}
    assert "validated_best_fit_mes_portfolio" not in registered


def test_level2_v2_clean_evidence_is_canonical_and_v1_is_superseded(root: Path) -> None:
    report = json.loads((
        root / "docs/reports/manual/level_02_stratified_benchmark_v2_clean_20260820.json"
    ).read_text(encoding="utf-8"))
    assert report["functional_gate"]["status"] == "PASS"
    assert report["provenance_gate"]["status"] == "PASS"
    assert report["governance_decision"] == "CANONICAL_PROMOTION_ALLOWED"
    assert report["promotion_to_canonical_allowed"] is True
    assert report["case_count"] == 84
    assert report["execution_count"] == 756
    assert len(report["strata"]) == 3
    assert all(len(value["artifact_locks"]) == 4 for value in report["strata"])
    assert all(value["git_dirty"] is False for value in report["strata"])
    assert sum(value["deterministic_group_count"] for value in report["strata"]) == 252

    registry = yaml.safe_load((
        root / "config/level_02/benchmarks/registry.yaml"
    ).read_text(encoding="utf-8-sig"))
    entries = {value["benchmark_id"]: value for value in registry["benchmarks"]}
    legacy = entries["level_02_generated_canonical_v1"]
    assert legacy["kind"] == "superseded"
    assert legacy["run_mode"] == "read_only"
    assert legacy["governance_status"] == "superseded"
    assert legacy["replacement_id"] == "level_02_generated_random_v2_candidate"
    for benchmark_id in (
        "level_02_generated_random_v2_candidate",
        "level_02_generated_stress_v2_candidate",
        "level_02_generated_prefix_v2_candidate",
    ):
        assert entries[benchmark_id]["kind"] == "canonical"
        assert entries[benchmark_id]["governance_status"].startswith(
            "canonical_active"
        )
    assert entries["level_02_generated_quick_v3"]["kind"] == "research"
    assert entries["level_02_generated_quick_v3"]["governance_status"] == "smoke_only"


def test_mes_level4_5_review_locks_its_declared_sources(root: Path) -> None:
    report = json.loads((
        root / "docs/reports/manual/level_04_05_mes_comparator_review_20260820.json"
    ).read_text(encoding="utf-8"))
    assert report["decision"] == "ACCEPTED_COMPARATOR_NOT_DEFAULT"
    assert report["default_algorithm"] == "extreme_point_best_fit"
    assert report["portfolio_v1"] == "NOT_PROMOTED"
    for source in report["source_evidence"]:
        path = root / source["path"]
        assert path.is_file()
        assert sha256(path.read_bytes()).hexdigest() == source["sha256"]


def test_level3_documents_do_not_claim_runtime_is_unregistered(root: Path) -> None:
    paths = (
        root / "docs/levels/level_03.md",
        root / "docs/specs/level3/level3_data_contract.md",
        root / "src/container_packing/levels/level_03_validation.py",
    )
    combined = "\n".join(path.read_text(encoding="utf-8-sig") for path in paths)
    stale_claims = (
        "Status: planned contract; no Level 3 processor or solver consumes it yet.",
        "intentionally not registered as an executable level yet",
    )
    assert all(claim not in combined for claim in stale_claims)


def test_superseded_documents_are_not_reintroduced(root: Path) -> None:
    superseded_paths = (
        "docs/archive/level1/CODEX_IMPLEMENTATION_SPEC_LEVEL1.md",
        "docs/specs/level1/level1_codex_implementation_spec.md",
        "docs/reports/manual/level_07_scale_acceptance_template.md",
        "docs/reports/manual/level_08_sequential_replay_protocol.md",
    )
    for relative_path in superseded_paths:
        assert not (root / relative_path).exists()


def test_level7_and_level8_canonical_docs_link_to_declared_evidence(root: Path) -> None:
    expected = {
        "level_07": (
            "docs/reports/manual/level_07_balance_fixture_baseline.md",
            "docs/reports/manual/level_07_scale_baseline.md",
        ),
        "level_08": (
            "docs/reports/manual/level_08_fixture_baseline.md",
            "docs/reports/manual/level_08_sequential_scale_baseline.md",
            "docs/reports/manual/level_08_soft_stop_affinity_gate_20260803.md",
        ),
    }
    for level_id, evidence_paths in expected.items():
        text = (root / f"docs/levels/{level_id}.md").read_text(encoding="utf-8-sig")
        for evidence_path in evidence_paths:
            assert (root / evidence_path).is_file()
            assert evidence_path in text


def test_level7_fixture_only_adr_is_marked_superseded(root: Path) -> None:
    text = (root / "docs/decisions/ADR-0023-level7-runtime-candidate-gate.md").read_text(
        encoding="utf-8-sig"
    )
    assert "Superseded." in text
    assert "docs/levels/level_07.md" in text


def test_canonical_docs_do_not_reference_superseded_documents(root: Path) -> None:
    forbidden = (
        "level1_codex_implementation_spec.md",
        "level_07_scale_acceptance_template.md",
        "level_08_sequential_replay_protocol.md",
    )
    paths = (root / "README.md", root / "docs/index.md", *sorted((root / "docs/levels").glob("*.md")))
    combined = "\n".join(path.read_text(encoding="utf-8-sig") for path in paths)
    assert all(name not in combined for name in forbidden)
