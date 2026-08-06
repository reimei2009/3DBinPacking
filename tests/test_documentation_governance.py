from __future__ import annotations

import re
from pathlib import Path

import yaml

from container_packing.algorithms.registry import get_algorithm
from container_packing.levels.registry import list_levels


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
    for base in (root / "src", root / "docs"):
        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".py", ".md"}:
                continue
            text = path.read_text(encoding="utf-8-sig")
            if any(marker in text for marker in _MOJIBAKE_MARKERS):
                offenders.append(str(path.relative_to(root)))
    assert offenders == []


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
