"""Tổng hợp evidence KPI/MES/repair Level 2 từ benchmark run đã chỉ định rõ."""

from __future__ import annotations

from ast import literal_eval
import json
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from ..algorithms.search.secondary_score import calculate_secondary_search_score
from ..data_loader import load_containers, load_placements
from ..provenance import sha256_file
from ..runtime.project import find_project_root


_KEYS = ("algorithm", "item_count", "item_selection_strategy", "item_selection_seed")


def build_level2_kpi_acceptance_report(
    *, control_run: str | Path, kpi_runs: Iterable[str | Path], repair_run: str | Path,
) -> dict[str, Any]:
    """Build a deterministic report; never discovers a 'latest' run implicitly."""

    root = find_project_root()
    control = _read_run("control", control_run, root)
    kpi = [_read_run("kpi", value, root) for value in kpi_runs]
    if not kpi:
        raise ValueError("At least one --kpi-run is required")
    repair = _read_run("repair", repair_run, root)
    _assert_comparable_inputs(control, [*kpi, repair])

    control_rows = _index_rows(control["rows"])
    kpi_rows = _index_rows(pd.concat([value["rows"] for value in kpi], ignore_index=True))
    repair_rows = _index_rows(repair["rows"])
    kpi_comparisons = _compare_rows(control_rows, kpi_rows)
    repair_comparisons = _compare_rows(control_rows, repair_rows)
    mes_fast = _mes_fast_comparator(control_rows)
    all_runs = [control, *kpi, repair]
    deterministic = all(value["deterministic"] for value in all_runs)
    all_successful = all(value["all_successful"] for value in all_runs)
    kpi_loss_free = bool(kpi_comparisons) and not any(
        value["outcome"] == "LOSS" for value in kpi_comparisons
    )
    repair_wins = sum(value["outcome"] == "WIN" for value in repair_comparisons)
    repair_loss_free = bool(repair_comparisons) and not any(
        value["outcome"] == "LOSS" for value in repair_comparisons
    )
    kpi_counts = sorted({value["item_count"] for value in kpi_comparisons})
    promotion = {
        "kpi_promotion": _gate_status(
            all_successful and deterministic and kpi_loss_free and 500 in kpi_counts,
            "PASS" if 500 in kpi_counts else "PENDING_KPI_500_GATE",
        ),
        "mes_fast_comparator": _gate_status(
            all_successful and deterministic and mes_fast["nonworse_official_objective"]
            and mes_fast["p95_runtime_ratio_to_best_fit"] <= 2.0,
            "FAIL",
        ),
        "repair_fallback": _gate_status(
            all_successful and deterministic and repair_loss_free and repair_wins > 0,
            "FAIL",
        ),
    }
    return {
        "schema_version": "1.0",
        "level": "level_02",
        "official_objective": "used_container_count_then_total_container_cost",
        "encoded_solver_objective_role": "legacy_compatibility_only",
        "runs": [{key: value for key, value in run.items() if key != "rows"} for run in all_runs],
        "deterministic": deterministic,
        "all_successful": all_successful,
        "kpi_comparisons": kpi_comparisons,
        "repair_comparisons": repair_comparisons,
        "mes_fast_comparator": mes_fast,
        "promotion": promotion,
        "diagnostic_note": (
            "diagnostic_secondary_score chỉ là KPI quan sát hoặc tie-break sau objective chính thức; "
            "không được dùng để đổi số container hoặc chi phí."
        ),
    }


def write_level2_kpi_acceptance_report(
    report: dict[str, Any], output_prefix: str | Path,
) -> tuple[Path, Path]:
    prefix = Path(output_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path, markdown_path = prefix.with_suffix(".json"), prefix.with_suffix(".md")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    rows = [
        "# Evidence KPI/MES/repair — Level 2", "",
        "- Objective chính thức: `(used_container_count, total_container_cost)`.",
        "- `encoded_solver_objective` chỉ để tương thích artifact cũ, không dùng xếp hạng.",
        f"- Tất cả run thành công: `{report['all_successful']}`; deterministic: `{report['deterministic']}`.",
        "", "## Promotion policy", "",
        "| Hạng mục | Kết quả |", "|---|---|",
    ]
    rows.extend(f"| {key} | `{value}` |" for key, value in report["promotion"].items())
    rows.extend(["", "## So sánh official objective", "", "| Nhóm | Algorithm | Items | Selection | Kết quả | Runtime ratio |", "|---|---|---:|---|---|---:|"])
    for group, values in (("KPI", report["kpi_comparisons"]), ("Repair", report["repair_comparisons"])):
        for value in values:
            rows.append(
                f"| {group} | {value['algorithm']} | {value['item_count']} | {value['item_selection_strategy']} | "
                f"{value['outcome']} | {value['runtime_ratio_to_control']:.3f} |"
            )
    rows.extend(["", "## MES", "", f"- p95 runtime ratio MES/Best Fit: `{report['mes_fast_comparator']['p95_runtime_ratio_to_best_fit']:.3f}`."])
    markdown_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return json_path, markdown_path


def _read_run(label: str, run_dir: str | Path, root: Path) -> dict[str, Any]:
    path = Path(run_dir)
    path = path if path.is_absolute() else root / path
    path = path.resolve()
    results_path, manifest_path = path / "benchmark" / "results.csv", path / "manifest.json"
    if not results_path.is_file() or not manifest_path.is_file():
        raise ValueError(f"{label}: expected benchmark/results.csv and manifest.json under {path}")
    frame = pd.read_csv(results_path, encoding="utf-8-sig")
    required = {*_KEYS, "repeat", "success", "validation_valid", "official_objective", "placement_signature", "algorithm_runtime_seconds", "selected_item_ids_checksum"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{label}: missing result columns: {', '.join(missing)}")
    success = frame["success"].map(_as_bool) & frame["validation_valid"].map(_as_bool)
    if not bool(success.all()):
        raise ValueError(f"{label}: report requires only independently VALID successful rows")
    if frame["official_objective"].isna().any():
        raise ValueError(f"{label}: successful row is missing official objective")
    deterministic = _is_deterministic(frame)
    _attach_diagnostics(frame, root)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    usage = manifest.get("dataset_usage", {})
    return {
        "label": label,
        "run_dir": _portable(path, root),
        "results_checksum": sha256_file(results_path),
        "dataset_checksums": {
            "items": usage.get("items_checksum"), "containers": usage.get("containers_checksum"),
        },
        "row_count": len(frame), "all_successful": True, "deterministic": deterministic,
        "rows": frame,
    }


def _attach_diagnostics(frame: pd.DataFrame, root: Path) -> None:
    for column in ("diagnostic_secondary_utilization_concentration", "diagnostic_secondary_internal_void_ratio", "diagnostic_secondary_minimum_support_margin"):
        if column not in frame:
            frame[column] = None
    for index, row in frame.iterrows():
        if pd.notna(row["diagnostic_secondary_utilization_concentration"]):
            continue
        run_dir = root / str(row["experiment_run_dir"])
        score = calculate_secondary_search_score(
            load_placements(run_dir / "solution" / "placements.csv"),
            load_containers(run_dir / "input_snapshot" / "containers.csv"),
            support_threshold=float(row.get("support_threshold", 0.8)),
        ).as_dict()
        frame.loc[index, "diagnostic_secondary_utilization_concentration"] = score["utilization_concentration"]
        frame.loc[index, "diagnostic_secondary_internal_void_ratio"] = score["internal_void_ratio"]
        frame.loc[index, "diagnostic_secondary_minimum_support_margin"] = score["minimum_support_margin"]


def _index_rows(frame: pd.DataFrame) -> dict[tuple[Any, ...], pd.Series]:
    values: dict[tuple[Any, ...], pd.Series] = {}
    for key, group in frame.groupby(list(_KEYS), dropna=False, sort=True):
        values[key] = group.sort_values("repeat").iloc[0]
    return values


def _compare_rows(control: dict[tuple[Any, ...], pd.Series], candidate: dict[tuple[Any, ...], pd.Series]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key in sorted(set(control) & set(candidate)):
        baseline, treatment = control[key], candidate[key]
        if str(baseline["selected_item_ids_checksum"]) != str(treatment["selected_item_ids_checksum"]):
            raise ValueError(f"Selected-item checksum mismatch for {key}")
        before, after = _objective(baseline), _objective(treatment)
        outcome = "WIN" if after < before else "TIE" if after == before else "LOSS"
        rows.append({
            "algorithm": key[0], "item_count": int(key[1]), "item_selection_strategy": key[2],
            "item_selection_seed": None if pd.isna(key[3]) else int(key[3]),
            "baseline_objective": before, "candidate_objective": after, "outcome": outcome,
            "runtime_ratio_to_control": float(treatment["algorithm_runtime_seconds"]) / max(float(baseline["algorithm_runtime_seconds"]), 1e-12),
            "diagnostic_secondary_score": {
                "utilization_concentration": float(treatment["diagnostic_secondary_utilization_concentration"]),
                "internal_void_ratio": float(treatment["diagnostic_secondary_internal_void_ratio"]),
                "minimum_support_margin": float(treatment["diagnostic_secondary_minimum_support_margin"]),
            },
        })
    return rows


def _mes_fast_comparator(rows: dict[tuple[Any, ...], pd.Series]) -> dict[str, Any]:
    ratios: list[float] = []
    nonworse = True
    by_input: dict[tuple[Any, ...], dict[str, pd.Series]] = {}
    for key, row in rows.items():
        by_input.setdefault(key[1:], {})[key[0]] = row
    for values in by_input.values():
        if "extreme_point_best_fit" not in values or "maximal_space_best_fit" not in values:
            continue
        best, mes = values["extreme_point_best_fit"], values["maximal_space_best_fit"]
        nonworse &= _objective(mes) <= _objective(best)
        ratios.append(float(mes["algorithm_runtime_seconds"]) / max(float(best["algorithm_runtime_seconds"]), 1e-12))
    return {"nonworse_official_objective": nonworse, "p95_runtime_ratio_to_best_fit": float(pd.Series(ratios).quantile(0.95)) if ratios else float("inf")}


def _assert_comparable_inputs(control: dict[str, Any], others: Iterable[dict[str, Any]]) -> None:
    for other in others:
        if other["dataset_checksums"] != control["dataset_checksums"]:
            raise ValueError(f"Dataset checksum mismatch: control vs {other['label']}")


def _is_deterministic(frame: pd.DataFrame) -> bool:
    for _, group in frame.groupby(list(_KEYS), dropna=False, sort=True):
        if group["placement_signature"].nunique(dropna=False) != 1 or group["official_objective"].nunique(dropna=False) != 1:
            return False
    return True


def _objective(row: pd.Series) -> tuple[int, float]:
    value = literal_eval(str(row["official_objective"]))
    return int(value["used_container_count"]), float(value["total_container_cost"])


def _gate_status(passed: bool, failed_label: str) -> str:
    return "PASS" if passed else failed_label


def _as_bool(value: Any) -> bool:
    return value is True or str(value).strip().lower() in {"true", "1", "yes"}


def _portable(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)
