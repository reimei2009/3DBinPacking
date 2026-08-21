from __future__ import annotations

from pathlib import Path
import runpy


def _module(root: Path) -> dict[str, object]:
    return runpy.run_path(str(root / "scripts/run_quality_gate.py"), run_name="quality_gate_test")


def test_quality_gate_prepends_current_worktree_source(root: Path, monkeypatch) -> None:
    monkeypatch.setenv("PYTHONPATH", "existing-source")
    environment = _module(root)["worktree_environment"](root)
    assert environment["PYTHONPATH"].split(";")[0] == str((root / "src").resolve())


def test_quality_gate_verifies_current_import(root: Path) -> None:
    module = _module(root)
    environment = module["worktree_environment"](root)
    module["verify_import_source"](root, environment)


def test_quality_gate_declares_every_generated_profile_required_by_full_suite(root: Path) -> None:
    profiles = _module(root)["REQUIRED_SYNTHETIC_PROFILES"]
    assert {value[0] for value in profiles} == {
        "config/synthetic/scale_1k_100.yaml",
        "config/synthetic/fleet_500_t10.yaml",
        "config/synthetic/fleet_5000_t25.yaml",
        "config/synthetic/fleet_500_t10_i1000.yaml",
    }
