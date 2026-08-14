from pathlib import Path


WEB_DEMO_GENERATION_PROFILES = (
    "config/synthetic/fleet_500_t10.yaml",
    "config/synthetic/fleet_500_t10_i1000.yaml",
    "config/synthetic/fleet_5000_t25.yaml",
)


def test_docker_context_excludes_generated_and_runtime_artifacts(root: Path) -> None:
    patterns = {
        line.strip()
        for line in (root / ".dockerignore").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert {"data/interim/", "data/processed/", "outputs/"}.issubset(patterns)


def test_docker_build_materializes_all_small_web_demo_profiles(root: Path) -> None:
    dockerfile = (root / "Dockerfile").read_text(encoding="utf-8")
    copy_application = dockerfile.index("COPY . .")
    non_root_runtime = dockerfile.index("USER appuser")

    for profile in WEB_DEMO_GENERATION_PROFILES:
        generation = (
            "python scripts/generate_synthetic_instances.py "
            f"--profile {profile}"
        )
        generation_index = dockerfile.index(generation)
        assert copy_application < generation_index < non_root_runtime

    assert "--overwrite" not in dockerfile[copy_application:non_root_runtime]
