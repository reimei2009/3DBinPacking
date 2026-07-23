from pathlib import Path

from container_packing.runtime.project import find_project_root


def test_find_project_root_prefers_configured_runtime_root(root: Path, monkeypatch):
    """An installed package can still resolve assets from the deployment checkout."""
    monkeypatch.setenv("CONTAINER_PACKING_PROJECT_ROOT", str(root))

    resolved = find_project_root("/usr/local/lib/python3.11/site-packages/container_packing/levels/pipeline.py")

    assert resolved == root


def test_find_project_root_uses_working_directory_when_module_is_installed(root: Path, monkeypatch):
    monkeypatch.delenv("CONTAINER_PACKING_PROJECT_ROOT", raising=False)
    monkeypatch.chdir(root)

    resolved = find_project_root("/usr/local/lib/python3.11/site-packages/container_packing/levels/pipeline.py")

    assert resolved == root
