from pathlib import Path
import pytest

from container_packing.data_loader import load_config, load_containers, load_items
from container_packing.instance_data import prepare_instance


@pytest.fixture(scope="session")
def root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def level1_manifest(root):
    return prepare_instance(root, load_config(root / "config/level_01/default.yaml"))


@pytest.fixture(scope="session")
def level1_items(root, level1_manifest):
    return load_items(root / level1_manifest["items_csv"])


@pytest.fixture(scope="session")
def level1_containers(root, level1_manifest):
    return load_containers(root / level1_manifest["containers_csv"])
