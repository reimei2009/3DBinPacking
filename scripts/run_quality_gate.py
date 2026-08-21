"""Run repository checks while forcing imports from this worktree's ``src``."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


TARGETED_TESTS = (
    "tests/test_algorithm_registry.py",
    "tests/test_level_registry.py",
    "tests/test_documentation_governance.py",
    "tests/test_streamlit_app.py",
    "tests/test_level2_inventory_search.py",
    "tests/test_level3_inventory_search.py",
    "tests/test_level4_inventory_search.py",
    "tests/test_level5_inventory_search.py",
    "tests/test_productization_readiness.py",
)

REQUIRED_SYNTHETIC_PROFILES = (
    ("config/synthetic/scale_1k_100.yaml", "data/interim/synthetic/empirical_scale_1k_100_v1/generation_manifest.json"),
    ("config/synthetic/fleet_500_t10.yaml", "data/interim/synthetic/level_01_inventory_fleet_500_t10_v1/generation_manifest.json"),
    ("config/synthetic/fleet_5000_t25.yaml", "data/interim/synthetic/level_01_inventory_fleet_5000_t25_v1/generation_manifest.json"),
    ("config/synthetic/fleet_500_t10_i1000.yaml", "data/interim/synthetic/level_02_inventory_items_1000_fleet_500_t10_v1/generation_manifest.json"),
)


def worktree_environment(root: Path) -> dict[str, str]:
    environment = dict(os.environ)
    source = str((root / "src").resolve())
    current = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = source if not current else os.pathsep.join((source, current))
    return environment


def verify_import_source(root: Path, environment: dict[str, str]) -> None:
    command = [
        sys.executable, "-c",
        "import pathlib, container_packing; print(pathlib.Path(container_packing.__file__).resolve())",
    ]
    result = subprocess.run(command, cwd=root, env=environment, text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Cannot import container_packing")
    imported = Path(result.stdout.strip()).resolve()
    expected = (root / "src" / "container_packing").resolve()
    if expected not in imported.parents:
        raise RuntimeError(f"Imported {imported}, expected source below {expected}")


def run(command: list[str], *, root: Path, environment: dict[str, str]) -> None:
    completed = subprocess.run(command, cwd=root, env=environment)
    if completed.returncode:
        raise SystemExit(completed.returncode)


def prepare_required_test_data(root: Path, environment: dict[str, str]) -> None:
    for profile, manifest in REQUIRED_SYNTHETIC_PROFILES:
        if (root / manifest).is_file():
            continue
        run(
            [sys.executable, "scripts/generate_synthetic_instances.py", "--profile", profile],
            root=root,
            environment=environment,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=("targeted", "full", "all"), default="all")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    environment = worktree_environment(root)
    verify_import_source(root, environment)
    prepare_required_test_data(root, environment)
    if args.scope in {"targeted", "all"}:
        existing = [value for value in TARGETED_TESTS if (root / value).is_file()]
        run([sys.executable, "-m", "pytest", "-q", *existing], root=root, environment=environment)
    if args.scope in {"full", "all"}:
        run([sys.executable, "-m", "pytest", "-q"], root=root, environment=environment)
    run(["git", "diff", "--check"], root=root, environment=environment)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
