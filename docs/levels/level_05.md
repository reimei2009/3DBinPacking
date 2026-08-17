# Level 5 — Khả năng chịu tải và truyền tải trọng tĩnh

Trạng thái: **solver và inventory workflow đã qua gate prefix 20–500 kiện**.

Level 5 kế thừa toàn bộ Level 4 và bổ sung khả năng chịu tải của kiện cùng mô
hình truyền tải trọng thẳng đứng đệ quy. Objective chính thức vẫn theo thứ tự:

1. số container đã dùng;
2. tổng chi phí container khi số container bằng nhau.

## Ràng buộc đang hoạt động

- hình học, biên container, không chồng lấn và payload;
- xoay ngang `XYZ/YXZ`;
- exact support và base-center support;
- stackability, nhóm stack và số lớp tối đa;
- tải trọng truyền từ trên xuống dưới theo tỷ lệ diện tích tiếp xúc;
- giới hạn khối lượng được đỡ phía trên và quy tắc kiện dễ vỡ.

Mỗi candidate phải qua feasibility policy Level 5. Nghiệm complete còn phải được
validator độc lập tái dựng stack graph và tính lại toàn bộ load-transfer graph từ
items, containers và placements gốc. Solver state không được dùng làm bằng chứng
validation.

## Inventory workflow

Best Fit, FFD và MES Best Fit dùng chung `InventoryLevelAdapter`. Adapter tái sử
dụng precheck, subset search, validated incumbent, budget và canonical
consolidation; Level 5 chỉ cung cấp orientation, feasibility policy, validator và
support closure riêng.

Repair di chuyển toàn bộ exact-support closure. Đây là lựa chọn an toàn vì mọi
load-transfer edge đều phát sinh từ một tiếp xúc support; closure có thể lớn hơn
tập tối thiểu cần di chuyển nhưng không tách supporter khỏi dependent đang truyền
tải qua nó.

Hill Climbing và Simulated Annealing vẫn chạy ở chế độ catalog cố định. Khi bật
inventory search, hai thuật toán này phải fail rõ ràng và không fallback ngầm.

Profile promotion dùng corpus research 1.000 kiện/500 physical container:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_benchmark.py `
  --suite config\level_05\benchmarks\inventory_promotion_20_500_manual.yaml
```

Gate gồm 20, 100, 300 và 500 kiện; ba constructor; hai repeat. Repair tắt để đo
construction thuần. Mọi success phải independently `VALID`, dùng chung input
fingerprint trong cùng case và deterministic qua hai repeat.

Gate ngày 2026-08-14 đạt 24/24 lượt `VALID` và 12/12 nhóm
case–algorithm deterministic. Đây là gate kỹ thuật trên các case prefix, không
phải benchmark phân phối để kết luận một constructor tốt nhất cho mọi dữ liệu.

## Comparator contact/support index

Chỉ mục contact/support hiện là comparator nghiên cứu và mặc định tắt. Load-transfer
graph vẫn được tái tính đầy đủ; independent validator không sử dụng chỉ mục.

## Output và giới hạn

Pipeline ghi `load_bearing.csv`, `load_transfer.csv` và
`load_bearing_validation.json` trong run directory Level 5.

Capacity hiện là `synthetic_weight_factor_v1`, phục vụ nghiên cứu phần mềm và
không phải dữ liệu vật liệu đã kiểm định. Level 5 chưa mô hình hóa áp suất tiếp
xúc, moment uốn, biến dạng, rung động, tải động hoặc ổn định cơ học đầy đủ. Vì vậy
nghiệm `VALID` chỉ hợp lệ theo contract tĩnh của Level 5, không phải chứng nhận an
toàn vận chuyển thực tế.
