"""Gate và tổng hợp evidence cho ba tầng benchmark Level 2 V2."""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

import pandas as pd

from .distribution import build_determinism_evidence, build_pairwise_outcomes


_EXPECTED = {
    "random_distribution": {
        "corpus_id": "level_02_generated_1k_500_random_v2_candidate",
        "case_count": 60,
        "execution_count": 540,
    },
    "stress": {
        "corpus_id": "level_02_generated_1k_500_stress_v2_candidate",
        "case_count": 18,
        "execution_count": 162,
    },
    "prefix_regression": {
        "corpus_id": "level_02_generated_1k_500_prefix_regression_v2",
        "case_count": 6,
        "execution_count": 54,
    },
}
_ALGORITHMS = {
    "extreme_point_best_fit", "extreme_point_ffd", "maximal_space_best_fit",
}
_LOCKED_ARTIFACTS = {
    "manifest": "manifest.json",
    "results": "benchmark/results.csv",
    "determinism": "benchmark/determinism_evidence.csv",
    "pairwise": "benchmark/pairwise_outcomes.csv",
}


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _required_artifact_paths(run_dir: Path) -> dict[str, Path]:
    paths = {key: run_dir / relative for key, relative in _LOCKED_ARTIFACTS.items()}
    missing = [path.as_posix() for path in paths.values() if not path.is_file()]
    if missing:
        raise ValueError("Evidence bundle thiếu artifact bắt buộc: " + ", ".join(missing))
    return paths


def _portable_run_directory(run_dir: Path) -> str:
    parts = run_dir.resolve().parts
    if "outputs" in parts:
        return Path(*parts[parts.index("outputs"):]).as_posix()
    return run_dir.as_posix()


def _read_run(
    run_dir: Path, stratum: str, expected: dict[str, Any], *, expected_algorithms: set[str], repeats: int,
) -> tuple[dict[str, Any], pd.DataFrame]:
    artifact_paths = _required_artifact_paths(run_dir)
    manifest = json.loads(artifact_paths["manifest"].read_text(encoding="utf-8"))
    results = pd.read_csv(artifact_paths["results"])
    published_determinism = pd.read_csv(artifact_paths["determinism"])
    published_pairwise = pd.read_csv(artifact_paths["pairwise"])
    functional_errors: list[str] = []
    provenance_errors: list[str] = []
    if manifest.get("corpus_id") != expected["corpus_id"]:
        functional_errors.append("corpus_id không khớp")
    if int(manifest.get("case_count", -1)) != expected["case_count"]:
        functional_errors.append("số bài kiểm tra không khớp")
    if len(results) != expected["execution_count"]:
        functional_errors.append("số lượt chạy không khớp")
    if set(results.get("benchmark_stratum", pd.Series(dtype=str)).dropna()) != {stratum}:
        functional_errors.append("tầng benchmark trong kết quả không khớp")
    success = results["success"].fillna(False).astype(bool)
    if not success.all():
        functional_errors.append("có lượt chạy không thành công")
    if "validation_valid" not in results or not results["validation_valid"].fillna(False).astype(bool).all():
        functional_errors.append("có lượt chạy chưa independently VALID")
    objective_columns = (
        "official_objective", "objective_value", "used_container_count",
        "total_container_cost",
    )
    if any(
        ((~success) & results.get(column, pd.Series(index=results.index, dtype=float)).notna()).any()
        for column in objective_columns
    ):
        functional_errors.append("lượt thất bại vẫn có objective")
    for _, group in results.groupby("case_id", sort=True):
        case_id = str(group["case_id"].iloc[0])
        if group["input_fingerprint"].nunique() != 1:
            functional_errors.append(f"case {case_id} có nhiều input fingerprint")
            break
        if set(group["algorithm"].astype(str)) != expected_algorithms:
            functional_errors.append(f"case {case_id} không có đúng ba thuật toán")
            break
        if group.groupby("algorithm", sort=False).size().to_dict() != {
            algorithm: repeats for algorithm in group["algorithm"].drop_duplicates()
        }:
            functional_errors.append(f"case {case_id} không có đúng ba repeat cho mỗi thuật toán")
            break
        if (
            "selected_item_ids_checksum" not in group
            or group["selected_item_ids_checksum"].nunique() != 1
        ):
            functional_errors.append(f"case {case_id} không dùng cùng tập item giữa các thuật toán")
            break
    determinism = build_determinism_evidence(results)
    if len(determinism) != expected["case_count"] * 3:
        functional_errors.append("số nhóm deterministic không khớp")
    elif not determinism["deterministic"].fillna(False).all():
        functional_errors.append("objective hoặc placement signature không deterministic")
    if len(published_determinism) != expected["case_count"] * len(expected_algorithms):
        functional_errors.append("artifact deterministic có số nhóm không khớp")
    elif "deterministic" not in published_determinism or not published_determinism[
        "deterministic"
    ].fillna(False).astype(bool).all():
        functional_errors.append("artifact deterministic chứa nhóm không xác định")
    if published_pairwise.empty:
        functional_errors.append("artifact pairwise trống")

    source_commit = str(manifest.get("git_commit") or "").strip()
    if not source_commit:
        provenance_errors.append("manifest thiếu source commit")
    if manifest.get("git_dirty") is not False:
        provenance_errors.append("source run có git_dirty=true hoặc không khai báo sạch")
    artifact_locks = {
        key: {
            "path": _LOCKED_ARTIFACTS[key],
            "sha256": _file_sha256(path),
            "size_bytes": path.stat().st_size,
        }
        for key, path in artifact_paths.items()
    }
    return {
        "stratum": stratum,
        "run_dir": _portable_run_directory(run_dir),
        "corpus_id": manifest.get("corpus_id"),
        "case_count": int(results["case_id"].nunique()),
        "execution_count": len(results),
        "valid_execution_count": int(results["validation_valid"].fillna(False).sum()),
        "deterministic_group_count": int(determinism["deterministic"].fillna(False).sum()),
        "source_commit": source_commit or None,
        "git_dirty": manifest.get("git_dirty"),
        "artifact_locks": artifact_locks,
        "functional_errors": functional_errors,
        "provenance_errors": provenance_errors,
        "errors": [*functional_errors, *provenance_errors],
        "functional_passed": not functional_errors,
        "provenance_passed": not provenance_errors,
        "passed": not functional_errors,
    }, results


def build_stratified_evidence_for_protocol(
    run_dirs: dict[str, Path], *, level_id: str, expected: dict[str, dict[str, Any]],
    report_id: str, repeats: int = 3,
) -> dict[str, Any]:
    """Build stratified evidence for any level sharing the canonical V2 protocol."""
    if set(run_dirs) != set(expected):
        raise ValueError("Evidence requires random_distribution, stress and prefix_regression runs")
    strata: list[dict[str, Any]] = []
    frames: dict[str, pd.DataFrame] = {}
    for stratum in expected:
        evidence, results = _read_run(
            Path(run_dirs[stratum]), stratum, expected[stratum],
            expected_algorithms=_ALGORITHMS, repeats=repeats,
        )
        strata.append(evidence)
        frames[stratum] = results
    random_outcomes = build_pairwise_outcomes(frames["random_distribution"])
    pairwise = []
    baseline = "extreme_point_best_fit"
    for comparator in ("extreme_point_ffd", "maximal_space_best_fit"):
        rows = random_outcomes[
            random_outcomes[["algorithm_a", "algorithm_b"]].apply(
                lambda row: {str(row.iloc[0]), str(row.iloc[1])} == {baseline, comparator},
                axis=1,
            )
        ]
        outcomes = []
        for row in rows.itertuples(index=False):
            value = str(row.outcome_for_a)
            if str(row.algorithm_a) == baseline:
                value = {"WIN": "LOSS", "LOSS": "WIN"}.get(value, value)
            outcomes.append(value)
        pairwise.append({
            "comparator": comparator,
            "wins": outcomes.count("WIN"),
            "ties": outcomes.count("TIE"),
            "losses": outcomes.count("LOSS"),
        })
    source_commits = sorted({
        str(value["source_commit"]) for value in strata if value["source_commit"]
    })
    provenance_errors: list[str] = []
    if len(source_commits) != 1:
        provenance_errors.append("ba tầng không dùng cùng một source commit")
    provenance_errors.extend(
        f"{value['stratum']}: {error}"
        for value in strata
        for error in value["provenance_errors"]
    )
    functional_passed = all(value["functional_passed"] for value in strata)
    provenance_passed = (
        all(value["provenance_passed"] for value in strata)
        and not provenance_errors
    )
    promotion_allowed = functional_passed and provenance_passed
    return {
        "schema_version": "2.0",
        "report_id": report_id,
        "level_id": level_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if functional_passed else "FAIL",
        "functional_gate": {
            "status": "PASS" if functional_passed else "FAIL",
            "requirements": "84 bài, 756 lượt, VALID, fair fingerprint và deterministic",
        },
        "provenance_gate": {
            "status": "PASS" if provenance_passed else "FAIL",
            "source_commits": source_commits,
            "errors": provenance_errors,
            "requires_clean_source": True,
        },
        "governance_decision": (
            "CANONICAL_PROMOTION_ALLOWED"
            if promotion_allowed
            else "CANONICAL_PENDING_CLEAN_RERUN"
            if functional_passed
            else "FUNCTIONAL_GATE_FAILED"
        ),
        "promotion_to_canonical_allowed": promotion_allowed,
        "case_count": sum(value["case_count"] for value in strata),
        "execution_count": sum(value["execution_count"] for value in strata),
        "strata": strata,
        "random_distribution_pairwise_vs_best_fit": pairwise,
        "interpretation": {
            "random_distribution": "Nguồn chính cho kết luận chất lượng tổng quát.",
            "stress": "Báo riêng; không trộn vào tỷ lệ thắng của random.",
            "prefix_regression": "Chỉ phát hiện hồi quy theo thứ tự nguồn.",
            "provenance": "Functional PASS không đủ để promote khi source run còn git_dirty.",
        },
        "objective_governance": {
            "official_objective": ["used_container_count", "total_container_cost"],
            "secondary_tie_break_policy": "utilization_void_support_margin_v1",
            "secondary_tie_break_default_enabled": False,
            "secondary_tie_break_scope": "complete_independently_valid_official_ties_only",
        },
        "reference_semantics": {
            "proven_optimal": "chỉ khi có bằng chứng exact",
            "best_observed": "tốt nhất trên cùng input fingerprint",
            "aggregate_lower_bound": "cận capacity sơ bộ, không phải nghiệm hoặc proof",
        },
    }


def verify_stratified_evidence_checksums(
    report: dict[str, Any], run_dirs: dict[str, Path],
) -> tuple[str, ...]:
    """Verify a published evidence bundle without rewriting source artifacts."""
    errors: list[str] = []
    report_strata = {str(value["stratum"]): value for value in report.get("strata", [])}
    if set(report_strata) != set(run_dirs):
        return ("tập run directory không khớp report",)
    for stratum, run_dir in run_dirs.items():
        locks = report_strata[stratum].get("artifact_locks", {})
        for key, relative in _LOCKED_ARTIFACTS.items():
            expected = locks.get(key, {}).get("sha256")
            path = Path(run_dir) / relative
            if not path.is_file():
                errors.append(f"{stratum}/{key}: thiếu artifact")
            elif not expected:
                errors.append(f"{stratum}/{key}: report thiếu checksum")
            elif _file_sha256(path) != expected:
                errors.append(f"{stratum}/{key}: checksum mismatch")
    return tuple(errors)


def build_stratified_evidence(run_dirs: dict[str, Path]) -> dict[str, Any]:
    """Backward-compatible Level 2 V2 evidence builder."""
    return build_stratified_evidence_for_protocol(
        run_dirs,
        level_id="level_02",
        expected=_EXPECTED,
        report_id="level_02_stratified_benchmark_v2_candidate",
    )


def write_stratified_evidence(
    report: dict[str, Any], output_prefix: Path,
) -> tuple[Path, Path]:
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    json_path = output_prefix.with_suffix(".json")
    markdown_path = output_prefix.with_suffix(".md")
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )
    lines = [
        "# Benchmark Level 2 V2 phân tầng",
        "",
        f"- Functional gate: `{report['functional_gate']['status']}`",
        f"- Provenance gate: `{report['provenance_gate']['status']}`",
        f"- Quyết định governance: `{report['governance_decision']}`",
        f"- Tổng số bài: {report['case_count']}",
        f"- Tổng lượt chạy: {report['execution_count']}",
        "",
        "Ba tầng được báo riêng; stress và prefix không tham gia kết luận phân phối random.",
        "",
        "## Gate từng tầng",
        "",
    ]
    for value in report["strata"]:
        lines.append(
            f"- `{value['stratum']}`: functional "
            f"{'PASS' if value['functional_passed'] else 'FAIL'}, provenance "
            f"{'PASS' if value['provenance_passed'] else 'FAIL'} — "
            f"{value['case_count']} bài, {value['execution_count']} lượt, "
            f"commit `{value['source_commit']}`, git_dirty=`{value['git_dirty']}`."
        )
        for error in value["provenance_errors"]:
            lines.append(f"  - {error}")
    lines.extend(["", "## So sánh trên phân phối random", ""])
    for value in report["random_distribution_pairwise_vs_best_fit"]:
        lines.append(
            f"- `{value['comparator']}`: {value['wins']} thắng / "
            f"{value['ties']} hòa / {value['losses']} thua so với Best Fit."
        )
    lines.extend([
        "",
        "## Diễn giải governance",
        "",
        "V2 đã đạt gate chức năng nhưng chưa thay V1 vì các source run hiện tại được tạo "
        "khi working tree còn thay đổi. V1 tiếp tục là canonical; V2 giữ vai trò research "
        "candidate cho đến khi chạy lại sạch và toàn bộ checksum gate đạt.",
        "",
        "`proven_optimal` chỉ dành cho exact proof; `best_observed` chỉ là nghiệm tốt nhất "
        "trên cùng input fingerprint; aggregate lower bound chỉ là cận capacity sơ bộ.",
        "",
        "## Clean rerun bắt buộc trước promotion",
        "",
        "```powershell",
        ".\\.venv\\Scripts\\python.exe .\\scripts\\run_benchmark_corpus.py `",
        "  --corpus config\\level_02\\benchmarks\\generated_1k_500_random_candidate.yaml",
        "",
        ".\\.venv\\Scripts\\python.exe .\\scripts\\run_benchmark_corpus.py `",
        "  --corpus config\\level_02\\benchmarks\\generated_1k_500_stress_candidate.yaml",
        "",
        ".\\.venv\\Scripts\\python.exe .\\scripts\\run_benchmark_corpus.py `",
        "  --corpus config\\level_02\\benchmarks\\generated_1k_500_prefix_regression.yaml",
        "```",
    ])
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, markdown_path
