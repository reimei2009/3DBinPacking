# Level 3 — Xoay ngang

Trạng thái: **solver orientation đã được nghiệm thu; inventory-aware workflow đang ở gate promotion**.

Level 3 kế thừa geometry, payload, floor contact, exact base-support ratio và
base-center support của Level 2. Mỗi kiện có thể giữ chiều dài/rộng hoặc hoán
đổi hai chiều ngang; chiều cao không đổi:

| Mã | Kích thước hiệu dụng `(length, width, height)` |
| --- | --- |
| `XYZ` | `(l, w, h)` |
| `YXZ` | `(w, l, h)` |

## Contract đang hoạt động

- chọn đúng một orientation trong `XYZ/YXZ`;
- boundary và non-overlap theo kích thước sau xoay;
- payload, floor contact, exact support ratio và base-center support;
- orientation được lưu trong placement, scene, report và validation;
- mọi nghiệm complete phải qua independent validator Level 3.

Level này chưa kích hoạt vertical rotation, stackability, load-bearing, nesting,
fragility, center of gravity hoặc loading/unloading order. Exact geometric
support không phải chứng nhận ổn định vật lý đầy đủ.

## Inventory-aware workflow

Best Fit, FFD và Maximal Empty Spaces dùng chung `InventoryLevelAdapter` và
`InventorySearchOrchestrator` với Level 1–2. Level 3 chỉ cung cấp:

- horizontal orientation provider;
- exact-support feasibility policy;
- exact-support closure cho repair;
- independent candidate validator Level 3.

Orientation provider được dùng từ hard precheck, subset generation đến
construction và partial repack. Vì vậy kiện chỉ vừa sau khi xoay ngang không bị
loại nhầm bởi precheck fixed-orientation.

Hill Climbing, Simulated Annealing và MILP chưa hỗ trợ inventory orchestration.
Nếu bật `container_search` với các thuật toán này, runtime phải dừng với thông
báo rõ; không fallback sang catalog prefix.

Physical corpus promotion tái sử dụng đúng dữ liệu 1.000 kiện/500 container đã
qualification, nhưng processed data và output luôn nằm trong namespace
`level_03`. Không sao chép hoặc đổi tên provenance gốc.

## Solver và objective

- `extreme_point_best_fit`: practical primary;
- `extreme_point_ffd`: constructive comparator;
- `maximal_space_best_fit`: geometric comparator;
- Hill Climbing và Simulated Annealing: comparator không-inventory;
- `milp_big_m`: exact reference tối đa 5 kiện.

Official objective vẫn là `(số container đã dùng, tổng chi phí container)`.
Nghiệm incomplete, timeout hoặc invalid không có official objective.

## Gate promotion inventory

Chạy tuần tự 20 → 100 → 300 → 500 kiện. Mỗi case so sánh Best Fit, FFD và MES
qua hai repeat:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_benchmark.py `
  --suite config\level_03\benchmarks\inventory_promotion_20_500_manual.yaml
```

Mọi success phải independently `VALID`; hai repeat phải có cùng objective và
placement signature. Chỉ sau khi runtime gate hoàn thành mới xem xét expose
inventory controls Level 3 trên Streamlit.

## Giới hạn dữ liệu

Raw field `forced_orientation` được bảo toàn nhưng chưa có mapping semantics đã
xác minh. Solver sử dụng profile cấu hình tường minh `horizontal_rotatable`,
không suy đoán orientation từ field này.
