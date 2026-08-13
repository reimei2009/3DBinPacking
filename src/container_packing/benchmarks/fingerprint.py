"""Fingerprint ngữ nghĩa cho input và experiment benchmark."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Mapping

from ..dataset_usage import DatasetUsageEvidence
from ..provenance import sha256_file
from .suites import BenchmarkScenario


_SEMANTIC_SECTIONS = (
    "containers",
    "model",
    "validation",
    "support",
    "orientation",
    "stackability",
    "load_bearing",
    "nesting",
    "balance",
    "unloading",
    "sequential_simulation",
    "container_search",
)
_IGNORED_FILE_KEYS = frozenset({
    "output_root", "processed_dir", "manifest_json",
})


def canonical_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def semantic_input_payload(
    *,
    level_id: str,
    scenario: BenchmarkScenario,
    config: Mapping[str, Any],
    root: Path,
    selection: Mapping[str, Any],
    dataset_usage: DatasetUsageEvidence | None,
) -> dict[str, Any]:
    """Tạo payload bao phủ dữ liệu và mọi contract đang tác động nghiệm."""

    return {
        "level": level_id,
        "scenario_id": scenario.scenario_id,
        "item_count": scenario.item_count,
        "container_count": scenario.container_count,
        "item_selection_strategy": scenario.item_selection_strategy,
        "item_selection_seed": scenario.item_selection_seed,
        "selection": dict(selection),
        "semantic_contract": {
            key: config.get(key) for key in _SEMANTIC_SECTIONS if key in config
        },
        "referenced_file_checksums": referenced_semantic_file_checksums(
            config, root=root,
        ),
        "generation_manifest_checksum": (
            dataset_usage.generation_manifest_checksum
            if dataset_usage is not None else None
        ),
    }


def semantic_input_fingerprint(**kwargs: Any) -> str:
    return canonical_sha256(semantic_input_payload(**kwargs))


def experiment_fingerprint(
    *,
    input_fingerprint: str,
    algorithm_id: str,
    random_seed: int,
    config: Mapping[str, Any],
) -> str:
    algorithm_settings = (
        config.get("solver", {})
        if algorithm_id == "milp_big_m"
        else config.get("algorithms", {}).get(algorithm_id, {})
    )
    return canonical_sha256({
        "input_fingerprint": input_fingerprint,
        "algorithm_id": algorithm_id,
        "random_seed": random_seed,
        "algorithm_settings": algorithm_settings,
    })


def referenced_semantic_file_checksums(
    config: Mapping[str, Any], *, root: Path,
) -> dict[str, str]:
    """Hash catalog/mapping/rules file được config tham chiếu, bỏ output sinh ra."""

    values: dict[str, str] = {}

    def visit(value: Any, key_path: tuple[str, ...]) -> None:
        if isinstance(value, Mapping):
            for key, child in value.items():
                visit(child, (*key_path, str(key)))
            return
        if isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, (*key_path, str(index)))
            return
        if not isinstance(value, str) or not key_path:
            return
        leaf = key_path[-1]
        if leaf in _IGNORED_FILE_KEYS:
            return
        looks_like_file = (
            leaf.endswith("_file")
            or leaf.endswith("_csv")
            or leaf.endswith("_path")
            or leaf in {"rules_file", "items_source_mapping"}
        )
        if not looks_like_file:
            return
        path = Path(value)
        resolved = path if path.is_absolute() else root / path
        if resolved.is_file():
            values[".".join(key_path)] = sha256_file(resolved)

    visit(config, ())
    return dict(sorted(values.items()))
