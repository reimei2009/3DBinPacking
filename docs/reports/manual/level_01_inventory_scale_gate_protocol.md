# Protocol nghiệm thu scale gate inventory-aware — Level 1

## Mục tiêu

Protocol này xác nhận engine tìm subset container hoạt động có giới hạn trên kho
500 và 5.000 physical container. Đây là evidence cho orchestration inventory,
không phải chứng minh tối ưu toàn cục và không phải benchmark 100.000 item.

## Gate A — Inspection không gọi solver

Gate A xác minh manifest, checksum, schema, normalization, hard precheck,
lower bound và lazy subset preview. Không được gọi packing solver.

Lệnh đã kiểm tra catalog 5.000 container:

```powershell
.\.venv\Scripts\python.exe .\scripts\inspect_generated_dataset.py `
  --manifest data\interim\synthetic\level_01_inventory_fleet_5000_t25_v1\generation_manifest.json `
  --level level_01 `
  --intent inventory_scale_gate `
  --mode stream `
  --inventory-preview-items 20 `
  --inventory-preview-candidates 32
```

Kết quả ngày 2026-08-06: `VALID`; 5.000 physical container, 25 type tương
đương, 5 candidate lazy preview, tổng thời gian inventory gate `4.693s`. Solver
không được gọi. Run output cục bộ tham chiếu:
`20260806T065908958942Z__level_01__dataset_inspection__i100_c5000__seed95000`.

Chạy cùng lệnh với manifest `fleet_500_t10` trước khi nghiệm thu Gate B của
catalog 500 nếu catalog được generate lại.

## Gate B — Packing bounded, chạy thủ công

Best Fit là solver chính, FFD là comparator. Cả hai nhận cùng catalog đầy đủ;
`container_count: 1` là cardinality bắt đầu tìm, không phải prefix catalog.

```powershell
.\.venv\Scripts\python.exe .\scripts\run_benchmark.py `
  --suite config\level_01\benchmarks\inventory_fleet_500_manual.yaml
```

```powershell
.\.venv\Scripts\python.exe .\scripts\run_benchmark.py `
  --suite config\level_01\benchmarks\inventory_fleet_5000_manual.yaml
```

Gate 500 có 8 source run; Gate 5.000 có 4 source run. Các lệnh này không do
Codex tự chạy vì có solver benchmark và có thể sinh log/output đáng kể.

## Điều kiện pass để promote sang Level 2

- tất cả nghiệm complete là `VALID` từ independent validator Level 1;
- hai repeat cùng input tạo cùng selected subset, placement signature và objective;
- không materialize power set; `max_candidates_per_count` phải nhỏ hơn số
  physical container;
- timeout/incomplete có `objective_value: null` và termination reason rõ ràng;
- manifest/solver metadata ghi `inventory_fingerprint`, selected physical IDs,
  canonical type, declared type và candidate diagnostics.

Chỉ khi cả Gate A và Gate B đạt điều kiện trên mới bắt đầu compose policy support
của Level 2 với shared inventory orchestration.
