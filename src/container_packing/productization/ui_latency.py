"""Versioned, reproducible warm Streamlit rerun measurements."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import json
from pathlib import Path
from time import perf_counter
from typing import Any

import pandas as pd

from ..provenance import runtime_metadata, sha256_file
from ..runtime.run_context import create_run_directory


UI_RESPONSE_METRIC_VERSION = "warm_streamlit_rerun_v1"


def collect_warm_rerun_samples(
    rerun: Callable[[int], None],
    *,
    warmups: int,
    samples: int,
    clock: Callable[[], float] = perf_counter,
) -> tuple[list[float], list[float]]:
    """Measure serial reruns without dropping or rewriting any observation."""
    if warmups < 0:
        raise ValueError("warmups must be non-negative")
    if samples <= 0:
        raise ValueError("samples must be positive")
    warmup_values = [_measure_once(rerun, index, clock) for index in range(warmups)]
    measured = [
        _measure_once(rerun, warmups + index, clock) for index in range(samples)
    ]
    return warmup_values, measured


def summarize_ui_response_samples(samples: list[float]) -> dict[str, float | int]:
    if not samples:
        raise ValueError("UI response evidence requires at least one measured sample")
    values = pd.Series(samples, dtype=float)
    if values.isna().any() or (values < 0).any():
        raise ValueError("UI response samples must be finite non-negative seconds")
    return {
        "sample_count": int(len(values)),
        "minimum_seconds": float(values.min()),
        "p50_seconds": float(values.quantile(0.50)),
        "p95_seconds": float(values.quantile(0.95)),
        "maximum_seconds": float(values.max()),
    }


def run_streamlit_ui_response_measurement(
    *,
    root: Path,
    level_id: str,
    profile_id: str,
    warmups: int,
    samples: int,
    item_counts: tuple[int, int] = (100, 101),
    output_root: Path | None = None,
) -> Path:
    """Run AppTest serially and publish an isolated UI-latency evidence run."""
    try:
        from streamlit.testing.v1 import AppTest
    except ImportError as exc:  # pragma: no cover - environment diagnostic
        raise RuntimeError(
            "Streamlit testing is unavailable; install the project web extra"
        ) from exc

    project_root = root.resolve()
    app_path = project_root / "src/container_packing/web/streamlit_app.py"
    if not app_path.is_file():
        raise ValueError(f"Streamlit entrypoint does not exist: {app_path}")
    if len(item_counts) != 2 or any(value <= 0 for value in item_counts):
        raise ValueError("item_counts must contain two positive values")

    started = perf_counter()
    page = AppTest.from_file(str(app_path), default_timeout=60)
    page.run()
    cold_start_seconds = perf_counter() - started
    _raise_page_exception(page, "cold start")

    _select_by_key(page.selectbox, "level_id", level_id, page)
    profile_key = f"{level_id}_inventory_profile"
    _select_by_key(page.selectbox, profile_key, profile_id, page)

    def rerun(index: int) -> None:
        target = item_counts[index % 2]
        widget = _find_by_key(page.number_input, "item_count")
        widget.set_value(target)
        page.run()
        _raise_page_exception(page, f"warm rerun {index + 1}")

    warmup_values, measured = collect_warm_rerun_samples(
        rerun, warmups=warmups, samples=samples,
    )
    summary = summarize_ui_response_samples(measured)
    provenance = runtime_metadata(project_root)
    run_id, run_dir = create_run_directory(
        (output_root or project_root / "outputs").resolve(),
        level_id,
        "ui_response_profile",
        max(item_counts),
        500,
        0,
    )
    metrics_dir = run_dir / "metrics"
    metrics_dir.mkdir(parents=True)
    metrics = {
        "schema_version": "1.0",
        "metric_version": UI_RESPONSE_METRIC_VERSION,
        "measurement_scope": "server_side_streamlit_apptest_rerun",
        "includes_solver_runtime": False,
        "includes_browser_paint_or_network": False,
        "level_id": level_id,
        "profile_id": profile_id,
        "warmup_count": warmups,
        "warmup_seconds": warmup_values,
        "item_counts_alternated": list(item_counts),
        "cold_start_seconds": cold_start_seconds,
        "samples_seconds": measured,
        **summary,
    }
    metrics_path = metrics_dir / "ui_response.json"
    metrics_path.write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    manifest = {
        "project": "3d-container-packing",
        "run_type": "ui_response_profile",
        "run_id": run_id,
        "level": level_id,
        "profile_id": profile_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "SUCCESS",
        "metric_version": UI_RESPONSE_METRIC_VERSION,
        "metrics_file": "metrics/ui_response.json",
        "metrics_sha256": sha256_file(metrics_path),
        **provenance,
    }
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    return run_dir


def load_ui_response_evidence(
    run_dir: str | Path,
    *,
    expected_level: str,
    minimum_samples: int,
) -> dict[str, Any]:
    """Read and verify one immutable UI measurement run fail-closed."""
    source = Path(run_dir).resolve()
    manifest_path = source / "manifest.json"
    metrics_path = source / "metrics/ui_response.json"
    if not manifest_path.is_file() or not metrics_path.is_file():
        raise ValueError("UI evidence requires manifest.json and metrics/ui_response.json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read UI response evidence: {exc}") from exc
    if manifest.get("run_type") != "ui_response_profile":
        raise ValueError("UI evidence run_type must be ui_response_profile")
    if manifest.get("status") != "SUCCESS":
        raise ValueError("UI evidence status must be SUCCESS")
    if manifest.get("level") != expected_level or metrics.get("level_id") != expected_level:
        raise ValueError("UI evidence level does not match the shadow benchmark")
    if manifest.get("metric_version") != UI_RESPONSE_METRIC_VERSION:
        raise ValueError("Unsupported UI response metric version")
    if metrics.get("metric_version") != UI_RESPONSE_METRIC_VERSION:
        raise ValueError("UI metrics use an unsupported metric version")
    if manifest.get("git_dirty") is not False:
        raise ValueError("UI response evidence must come from a clean Git worktree")
    checksum = sha256_file(metrics_path)
    if manifest.get("metrics_sha256") != checksum:
        raise ValueError("UI response metrics checksum mismatch")
    measured = list(metrics.get("samples_seconds") or [])
    if len(measured) < minimum_samples:
        raise ValueError(
            f"UI response evidence requires at least {minimum_samples} measured samples"
        )
    recalculated = summarize_ui_response_samples([float(value) for value in measured])
    if abs(float(metrics.get("p95_seconds", -1)) - float(recalculated["p95_seconds"])) > 1e-12:
        raise ValueError("UI response p95 does not match the raw measured samples")
    return {
        "run_dir": str(source),
        "manifest": manifest,
        "metrics": metrics,
        "artifact_checksums": {
            "manifest.json": sha256_file(manifest_path),
            "metrics/ui_response.json": checksum,
        },
    }


def _measure_once(
    rerun: Callable[[int], None], index: int, clock: Callable[[], float],
) -> float:
    started = clock()
    rerun(index)
    elapsed = float(clock() - started)
    if elapsed < 0:
        raise ValueError("UI response clock moved backwards")
    return elapsed


def _find_by_key(values: Any, key: str) -> Any:
    try:
        return next(value for value in values if value.key == key)
    except StopIteration as exc:
        raise RuntimeError(f"Streamlit widget {key!r} was not rendered") from exc


def _select_by_key(values: Any, key: str, selected: str, page: Any) -> None:
    widget = _find_by_key(values, key)
    if widget.value != selected:
        try:
            # AppTest exposes formatted labels in ``options`` while ``set_value``
            # accepts the underlying ID used by Streamlit session state.
            widget.set_value(selected)
        except ValueError as exc:
            raise RuntimeError(
                f"Streamlit widget {key!r} does not accept {selected!r}"
            ) from exc
        page.run()
        _raise_page_exception(page, f"select {key}")


def _raise_page_exception(page: Any, stage: str) -> None:
    if page.exception:
        raise RuntimeError(f"Streamlit AppTest failed during {stage}: {page.exception[0]}")
