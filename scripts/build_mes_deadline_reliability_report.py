from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from container_packing.benchmarks.mes_deadline_reliability import (
    OFFICIAL_ARTIFACT_CHECKSUMS,
    OFFICIAL_SOURCE_COMMIT,
    evaluate_mes_deadline_reliability,
)
from container_packing.reporting import write_json, write_text


def _markdown(payload: dict[str, object], report_id: str) -> str:
    artifacts = payload["artifacts"]
    assert isinstance(artifacts, list)
    artifact_rows = "\n".join(
        "| {level} | `{corpus_id}` | `{run_id}` | `{manifest_sha256}` | `{results_sha256}` |".format(
            **artifact
        )
        for artifact in artifacts
    )
    longest = payload.get("longest_operation") or "không có"
    return f"""# Evidence độ tin cậy deadline MES

**Mã báo cáo:** `{report_id}`

**Quyết định:** `{payload['decision']}`

## Kết luận

Không cần mở batch cooperative deadline hardening và không cần subprocess watchdog. Trong
18 lượt chẩn đoán MES ở Level 4–5, toàn bộ nghiệm đều `FEASIBLE`, independently `VALID`,
deterministic và không có dấu hiệu sleep, tranh chấp tài nguyên máy hoặc gián đoạn đồng hồ.

Kết luận này chỉ đóng vấn đề **độ tin cậy deadline MES**. Constructor Portfolio V1 vẫn
`NOT_PROMOTED` vì gate runtime và deterministic Level 5 trước đó không đạt. MES tiếp tục là
research comparator; Level 6 tiếp tục đóng băng.

## Evidence đã khóa

- Lượt hợp lệ: **{payload['valid_execution_count']}/{payload['execution_count']}**.
- Nhóm case–algorithm deterministic: **{payload['deterministic_group_count']}**.
- Lượt nhiễu môi trường: **{payload['contaminated_execution_count']}**.
- Deadline overshoot lớn nhất: **{float(payload['maximum_clean_overshoot_seconds']):.6f} giây**.
- Operation dài nhất: **`{longest}`**, **{float(payload['maximum_clean_operation_seconds']):.8f} giây**.
- Operation cần harden: **{payload.get('operation_to_harden') or 'không có'}**.

| Level | Corpus | Run | SHA-256 manifest | SHA-256 results |
|---|---|---|---|---|
{artifact_rows}

Hai run đều được tạo từ commit sạch
`{artifacts[0]['source_commit']}`. Checksum trong bảng là khóa provenance: report phải fail
nếu manifest hoặc kết quả bị thiếu, thay đổi hay không còn khớp nguồn.

## Cách diễn giải

Deadline vẫn được quyết định theo wall-clock và không được tự gia hạn. Observer chỉ đo thêm
wall time, process CPU time và active time của Windows. Ngưỡng mở hardening là operation
active-time trên 1 giây hoặc overshoot sạch trên `max(1 giây, 1% deadline)`; evidence này
không chạm ngưỡng nào.

Không dùng report này để đảo ngược benchmark portfolio, xếp hạng chất lượng solver hoặc
tuyên bố MES tối ưu. Các run diagnostic không tham gia canonical ranking.
"""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate MES deadline reliability evidence for Level 4-5",
    )
    parser.add_argument("--level-04-run", required=True)
    parser.add_argument("--level-05-run", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--report-id", default="mes_deadline_reliability_20260820")
    parser.add_argument(
        "--expected-source-commit",
        default=OFFICIAL_SOURCE_COMMIT,
        help="Commit locked by the official evidence protocol",
    )
    args = parser.parse_args()
    decision = evaluate_mes_deadline_reliability(
        {
            "level_04": args.level_04_run,
            "level_05": args.level_05_run,
        },
        expected_source_commit=args.expected_source_commit,
        expected_checksums=OFFICIAL_ARTIFACT_CHECKSUMS,
    )
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    payload = decision.payload()
    payload = {
        "report_id": args.report_id,
        "evidence_scope": "mes_deadline_reliability_level_04_05",
        "source_commit": args.expected_source_commit,
        **payload,
        "portfolio_v1_status": "NOT_PROMOTED",
        "mes_role": "research_comparator",
        "level_06_status": "frozen",
    }
    write_json(output / f"{args.report_id}.json", payload)
    write_text(output / f"{args.report_id}.md", _markdown(payload, args.report_id))
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
