"""Tổng hợp evidence bất biến để nghiệm thu Level 2."""

from __future__ import annotations

from ast import literal_eval
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from ..provenance import sha256_file


MPV_EXPECTED_ALGORITHMS = ("extreme_point_best_fit", "extreme_point_ffd")
MPV_EXPECTED_DATASET_FAMILY = "mpv_fixed_orientation_exact_support"
MPV_EXPECTED_CASE_COUNT = 27
MPV_EXPECTED_REPEAT_COUNT = 2
MPV_EXPECTED_EXECUTION_COUNT = 108
CANONICAL_REFERENCE_KINDS = frozenset({
    "best_observed", "proven_optimal", "proven_infeasible", "unavailable",
})
LEGACY_REFERENCE_KINDS = frozenset({"best_known"})


@dataclass(frozen=True)
class AcceptanceEvidence:
    label: str
    run_dir: str
    results_checksum: str
    row_count: int
    successful_row_count: int
    all_successful: bool
    deterministic: bool
    objective_invariant_valid: bool
    maximum_algorithm_runtime_seconds: float | None
    peak_rss_max_bytes: int | None
    telemetry_complete: bool
    official_objectives: dict[str, dict[str, float | int]]
    placement_signatures: dict[str, list[str]]
    acquisition_ladders: tuple[str, ...]
    termination_reasons: tuple[str, ...]
    scenario_count: int
    algorithms: tuple[str, ...]
    dataset_families: tuple[str, ...]
    repeat_counts: tuple[int, ...]
    fingerprints_consistent_by_scenario: bool
    item_checksums_consistent_by_scenario: bool
    reference_kinds: tuple[str, ...]
    legacy_reference_kind_detected: bool
    pairwise_outcome_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def inspect_benchmark_run(label: str, run_dir: str | Path) -> AcceptanceEvidence:
    run_dir = Path(run_dir).resolve()
    results_path = run_dir / "benchmark" / "results.csv"
    if not results_path.is_file():
        raise ValueError(f"Benchmark results do not exist: {results_path}")
    frame = pd.read_csv(results_path, encoding="utf-8-sig")
    required = {
        "scenario_id", "algorithm", "random_seed", "repeat", "success",
        "validation_valid", "official_objective", "objective_value",
        "placement_signature", "algorithm_runtime_seconds",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"Benchmark {label} is missing columns: {', '.join(missing)}")

    success = frame["success"].map(_as_bool)
    validation = frame["validation_valid"].map(_as_bool)
    official = (
        frame["official_objective"].notna()
        & frame["official_objective"].astype(str).str.strip().ne("")
    )
    encoded = pd.to_numeric(frame["objective_value"], errors="coerce").notna()
    failure_leak = (~success) & (official | encoded)
    successful_contract = (~success) | (validation & official & encoded)
    invariant = not bool(failure_leak.any()) and bool(successful_contract.all())

    deterministic_keys = [value for value in (
        "scenario_id", "algorithm", "random_seed", "input_fingerprint",
    ) if value in frame.columns]
    deterministic = True
    successful = frame[success].copy()
    if not successful.empty:
        for _, group in successful.groupby(deterministic_keys, dropna=False, sort=True):
            deterministic &= group["placement_signature"].nunique(dropna=False) == 1
            deterministic &= group["official_objective"].astype(str).nunique(dropna=False) == 1

    runtime = pd.to_numeric(frame["algorithm_runtime_seconds"], errors="coerce")
    peak = _numeric_column(frame, "peak_rss_bytes")
    phase = frame.get("pipeline_phase_runtime_seconds")
    termination = frame.get("search_termination_reason")
    telemetry_complete = bool(
        runtime.notna().all()
        and peak is not None and peak.notna().all()
        and phase is not None and phase.notna().all()
        and phase.astype(str).str.strip().ne("").all()
        and termination is not None and termination.notna().all()
        and termination.astype(str).str.strip().ne("").all()
    )

    objective_map: dict[str, dict[str, float | int]] = {}
    signatures: dict[str, list[str]] = {}
    for (scenario_id, algorithm), group in successful.groupby(
        ["scenario_id", "algorithm"], dropna=False, sort=True,
    ):
        key = f"{scenario_id}|{algorithm}"
        objective_map[key] = _parse_official_objective(str(group.iloc[0]["official_objective"]))
        signatures[key] = sorted(
            str(value) for value in group["placement_signature"].dropna().unique()
        )

    ladder_column = frame.get("incumbent_acquisition_cardinality_ladder")
    ladders = () if ladder_column is None else tuple(sorted({
        str(value).strip() for value in ladder_column.dropna() if str(value).strip()
    }))
    reasons = () if termination is None else tuple(sorted({
        str(value).strip() for value in termination.dropna() if str(value).strip()
    }))
    reference_column = frame.get("reference_kind")
    reference_kinds = () if reference_column is None else tuple(sorted({
        str(value).strip() for value in reference_column.dropna() if str(value).strip()
    }))
    repeat_counts = tuple(sorted(
        int(value) for value in frame.groupby(
            ["scenario_id", "algorithm", "random_seed"], dropna=False,
        ).size().unique()
    ))
    pairwise_path = run_dir / "benchmark" / "pairwise_outcomes.csv"
    pairwise_counts: dict[str, int] = {}
    if pairwise_path.is_file():
        pairwise = pd.read_csv(pairwise_path, encoding="utf-8-sig")
        if "outcome_for_a" in pairwise.columns:
            pairwise_counts = {
                str(key): int(value)
                for key, value in pairwise["outcome_for_a"].value_counts().to_dict().items()
            }

    return AcceptanceEvidence(
        label=label,
        run_dir=_portable_path(run_dir),
        results_checksum=sha256_file(results_path),
        row_count=len(frame),
        successful_row_count=int(success.sum()),
        all_successful=bool(success.all() and validation.all()),
        deterministic=bool(deterministic),
        objective_invariant_valid=invariant,
        maximum_algorithm_runtime_seconds=(None if runtime.dropna().empty else float(runtime.max())),
        peak_rss_max_bytes=(None if peak is None or peak.dropna().empty else int(peak.max())),
        telemetry_complete=telemetry_complete,
        official_objectives=objective_map,
        placement_signatures=signatures,
        acquisition_ladders=ladders,
        termination_reasons=reasons,
        scenario_count=int(frame["scenario_id"].nunique(dropna=False)),
        algorithms=tuple(sorted(str(value) for value in frame["algorithm"].unique())),
        dataset_families=_unique_strings(frame.get("dataset_family")),
        repeat_counts=repeat_counts,
        fingerprints_consistent_by_scenario=_one_value_per_scenario(frame, "input_fingerprint"),
        item_checksums_consistent_by_scenario=_one_value_per_scenario(
            frame, "selected_item_ids_checksum",
        ),
        reference_kinds=reference_kinds,
        legacy_reference_kind_detected=bool(set(reference_kinds) & LEGACY_REFERENCE_KINDS),
        pairwise_outcome_counts=pairwise_counts,
    )


def build_level2_acceptance_report(
    *, internal_runs: Iterable[tuple[str, str | Path]],
    mpv_run: str | Path | None = None,
) -> dict[str, Any]:
    evidence = [inspect_benchmark_run(label, path) for label, path in internal_runs]
    mpv_evidence = inspect_benchmark_run("mpv_fixed_orientation", mpv_run) if mpv_run else None
    internal_pass = all(
        value.all_successful and value.deterministic
        and value.objective_invariant_valid and value.telemetry_complete
        for value in evidence
    )
    mpv_protocol_checks = _mpv_protocol_checks(mpv_evidence)
    mpv_pass = bool(mpv_evidence and all(mpv_protocol_checks.values()))
    if not internal_pass:
        status = "FAIL_INTERNAL_ACCEPTANCE"
    elif mpv_evidence is None:
        status = "BLOCKED_EXTERNAL_CORPUS"
    elif not mpv_pass:
        status = "FAIL_MPV_ACCEPTANCE"
    else:
        status = "PASS"
    return {
        "schema_version": "1.1",
        "level": "level_02",
        "status": status,
        "internal_acceptance_passed": internal_pass,
        "mpv_acceptance_passed": mpv_pass,
        "mpv_protocol_checks": mpv_protocol_checks,
        "promotion_inventory_orchestration_to_level_03_allowed": status == "PASS",
        "objective_semantics": "used_container_count_then_total_container_cost",
        "encoded_solver_objective_role": "legacy_compatibility_only",
        "mpv_semantics": "fixed_orientation_with_level_02_exact_support",
        "mpv_external_best_known_comparison_allowed": False,
        "mpv_best_known_comparison_allowed": False,
        "reference_semantics": {
            "best_observed": "best valid objective observed for the same input fingerprint in this corpus run",
            "best_known": "legacy label; readable but not accepted for new Level 2 evidence",
        },
        "evidence": [value.to_dict() for value in evidence],
        "mpv_evidence": None if mpv_evidence is None else mpv_evidence.to_dict(),
    }


def write_level2_acceptance_report(
    report: dict[str, Any], output_prefix: str | Path,
) -> tuple[Path, Path]:
    prefix = Path(output_prefix)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = prefix.with_suffix(".json")
    markdown_path = prefix.with_suffix(".md")
    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    rows = [
        "# Nghiệm thu Level 2", "",
        f"- Trạng thái: `{report['status']}`",
        f"- Gate nội bộ: `{'PASS' if report['internal_acceptance_passed'] else 'FAIL'}`",
        f"- Gate MPV: `{'PASS' if report['mpv_acceptance_passed'] else 'CHƯA ĐẠT'}`",
        "- Cho phép lập kế hoạch promote inventory orchestration sang Level 3: "
        f"`{str(report['promotion_inventory_orchestration_to_level_03_allowed']).lower()}`",
        "- Objective chính thức: `(used_container_count, total_container_cost)`.",
        "- Scalar encoded chỉ dùng để đọc artifact legacy.",
        "- MPV được đánh giá với fixed orientation và exact support của Level 2.",
        "- `best_observed` chỉ là nghiệm tốt nhất quan sát được trên cùng input fingerprint "
        "trong run này; không phải best-known MPV gốc và không chứng minh tối ưu.",
        "", "## Evidence", "",
        "| Nhóm | Rows | Thành công | Deterministic | Objective invariant | Telemetry | Runtime lớn nhất (s) | Peak RSS (bytes) |",
        "|---|---:|---:|---|---|---|---:|---:|",
    ]
    values = [*report["evidence"]]
    if report["mpv_evidence"] is not None:
        values.append(report["mpv_evidence"])
    for value in values:
        runtime = value["maximum_algorithm_runtime_seconds"]
        rows.append(
            f"| {value['label']} | {value['row_count']} | {value['successful_row_count']} | "
            f"{value['deterministic']} | {value['objective_invariant_valid']} | "
            f"{value['telemetry_complete']} | {'' if runtime is None else f'{runtime:.3f}'} | "
            f"{'' if value['peak_rss_max_bytes'] is None else value['peak_rss_max_bytes']} |"
        )
    if report["mpv_evidence"] is not None:
        rows.extend(["", "## Kiểm tra protocol MPV", ""])
        for name, passed in report["mpv_protocol_checks"].items():
            rows.append(f"- `{name}`: `{'PASS' if passed else 'FAIL'}`")
    if report["status"] == "BLOCKED_EXTERNAL_CORPUS":
        rows.extend([
            "", "## Blocker", "",
            "Chưa có bundle MPV local cùng checksum tin cậy, vì vậy Level 2 chưa "
            "được đóng và chưa được phép lập kế hoạch promote Level 3.",
        ])
    markdown_path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return json_path, markdown_path


def _mpv_protocol_checks(evidence: AcceptanceEvidence | None) -> dict[str, bool]:
    if evidence is None:
        return {}
    return {
        "execution_count_108": evidence.row_count == MPV_EXPECTED_EXECUTION_COUNT,
        "successful_and_independently_valid": evidence.all_successful,
        "case_count_27": evidence.scenario_count == MPV_EXPECTED_CASE_COUNT,
        "algorithms_best_fit_and_ffd": evidence.algorithms == MPV_EXPECTED_ALGORITHMS,
        "two_repeats_per_case_algorithm": evidence.repeat_counts == (MPV_EXPECTED_REPEAT_COUNT,),
        "deterministic_signature_and_objective": evidence.deterministic,
        "objective_null_on_failure": evidence.objective_invariant_valid,
        "one_fingerprint_per_case": evidence.fingerprints_consistent_by_scenario,
        "one_item_checksum_per_case": evidence.item_checksums_consistent_by_scenario,
        "dataset_family_is_mpv": evidence.dataset_families == (MPV_EXPECTED_DATASET_FAMILY,),
        "telemetry_peak_memory_and_termination_complete": evidence.telemetry_complete,
        "canonical_best_observed_reference": evidence.reference_kinds == ("best_observed",),
        "no_legacy_reference_kind": not evidence.legacy_reference_kind_detected,
        "best_fit_pairwise_outcomes_1_25_1": evidence.pairwise_outcome_counts == {
            "WIN": 1, "TIE": 25, "LOSS": 1,
        },
    }


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def _numeric_column(frame: pd.DataFrame, name: str) -> pd.Series | None:
    column = frame.get(name)
    return None if column is None else pd.to_numeric(column, errors="coerce")


def _unique_strings(column: pd.Series | None) -> tuple[str, ...]:
    if column is None:
        return ()
    return tuple(sorted({str(value).strip() for value in column.dropna() if str(value).strip()}))


def _one_value_per_scenario(frame: pd.DataFrame, column_name: str) -> bool:
    if column_name not in frame.columns:
        return False
    column = frame[column_name]
    if column.isna().any() or column.astype(str).str.strip().eq("").any():
        return False
    counts = frame.groupby("scenario_id", dropna=False)[column_name].nunique(dropna=False)
    return bool((counts == 1).all())


def _portable_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def _parse_official_objective(value: str) -> dict[str, float | int]:
    try:
        parsed = literal_eval(value)
    except (SyntaxError, ValueError) as exc:
        raise ValueError(f"Invalid official_objective payload: {value!r}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("official_objective must contain a mapping")
    count = int(parsed.get("used_container_count"))
    cost = float(parsed.get("total_container_cost"))
    if count <= 0 or cost < 0:
        raise ValueError("official_objective contains invalid count or cost")
    return {"used_container_count": count, "total_container_cost": cost}
