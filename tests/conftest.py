from pathlib import Path
import pytest

from container_packing.data_loader import load_config, load_containers, load_items
from container_packing.instance_data import prepare_instance


def pytest_collection_modifyitems(items):
    """Gắn đúng một tầng test chính theo tên module, tập trung tại một nơi."""
    for item in items:
        name = Path(str(item.fspath)).name.lower()
        if "streamlit" in name or "_web" in name or name.startswith("test_web"):
            marker = pytest.mark.web
        elif any(token in name for token in (
            "acceptance", "scale_gate", "benchmark_corpus", "large_synthetic",
        )):
            marker = pytest.mark.acceptance
        elif any(token in name for token in (
            "milp", "extreme_point", "maximal_space", "hill_climbing",
            "simulated_annealing", "solver", "feasibility_policy",
            "container_assignment", "consolidation",
        )):
            marker = pytest.mark.solver
        elif any(token in name for token in (
            "pipeline", "runtime", "cli", "benchmark", "experiment", "integration",
            "inventory_search", "inventory_orchestration", "application_service",
            "dataset_inspection", "dataset_usage", "dynamic_instance",
            "level3_", "level4_", "level5_", "level6_", "level7_", "level8_",
        )):
            marker = pytest.mark.integration
        else:
            marker = pytest.mark.unit
        item.add_marker(marker)


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
