from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from container_packing.benchmarks.mes_deadline_reliability import (
    evaluate_mes_deadline_reliability,
)
from container_packing.reporting import write_json, write_text


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate MES deadline reliability evidence for Level 4-5",
    )
    parser.add_argument("--level-04-run", required=True)
    parser.add_argument("--level-05-run", required=True)
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()
    decision = evaluate_mes_deadline_reliability({
        "level_04": args.level_04_run,
        "level_05": args.level_05_run,
    })
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    payload = decision.payload()
    write_json(output / "mes_deadline_reliability_report.json", payload)
    write_text(
        output / "mes_deadline_reliability_report.md",
        "# Evidence độ tin cậy deadline MES\n\n"
        f"- Quyết định: `{decision.decision}`\n"
        f"- Lượt chẩn đoán: {decision.execution_count}\n"
        f"- Lượt nhiễu môi trường: {decision.contaminated_execution_count}\n"
        f"- Operation active-time dài nhất: {decision.maximum_clean_operation_seconds:.6f} giây\n"
        f"- Overshoot sạch lớn nhất: {decision.maximum_clean_overshoot_seconds:.6f} giây\n"
        f"- Operation cần harden: {decision.operation_to_harden or 'không có'}\n\n"
        "Run bị sleep, contention hoặc clock discontinuity không bị sửa/xóa; "
        "nếu cần acceptance phải tạo recovery run mới.\n",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
