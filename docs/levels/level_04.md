# Level 4 — Quy tắc xếp chồng

> Candidate đang đánh giá: portfolio bounded Best Fit + MES có independent
> validation. Portfolio chưa phải mặc định, repair bị tắt và chưa expose trên UI.

## Trạng thái

Level 4 đã có orientation ngang, exact support, stackability policy, independent
validator và năm heuristic/metaheuristic. Shared inventory orchestration cho
Best Fit, FFD và MES là promotion candidate cho đến khi gate 20–500 hoàn tất.

## Contract đang hoạt động

Level 4 kế thừa toàn bộ Level 3:

- hộp chữ nhật, payload, boundary và non-overlap;
- orientation ngang `XYZ/YXZ`;
- floor contact, exact union support area và base-center support.

Level 4 bổ sung quy tắc nghiệp vụ về xếp chồng:

- item cha và con trực tiếp phải có cùng `stackability_code`;
- item không nằm trên sàn phải có đúng một cha trực tiếp được khai báo;
- cha được chọn deterministic theo diện tích tiếp xúc lớn nhất, sau đó item ID;
- số lớp không vượt `max_stackability` nhỏ nhất trên chuỗi cha–con;
- item được khai báo non-stackable chỉ được làm root trên sàn và không có con.

Contract canonical nằm tại `config/level_04/stackability_rules.yaml`. Semantics
`maximum_layers_in_parent_chain_including_root` là quy ước versioned của dự án
vì nguồn dữ liệu không định nghĩa chi tiết trường `max_stackability`.

## Solver và inventory

- `extreme_point_best_fit`: practical solver.
- `extreme_point_ffd`: constructive comparator deterministic.
- `maximal_space_best_fit`: comparator dùng maximal empty spaces.
- Hill Climbing và Simulated Annealing chỉ chạy theo flow không-inventory.

Khi `container_search.enabled=true`, chỉ ba constructive solver đầu được dùng.
Chúng cùng gọi `InventoryLevelAdapter`, horizontal orientation provider,
`ExactSupportStackabilityPolicy` và Level 4 validator. Thuật toán không tương
thích phải fail rõ ràng, không fallback sang catalog prefix.

Repair là tùy chọn. Support closure giữ supporter và toàn bộ dependent trong
cùng cụm, nên stack parent/child không bị tách trong partial repack. Candidate
chỉ trở thành incumbent khi complete, independently `VALID` và tốt hơn theo:

```text
(used_container_count, total_container_cost)
```

## Dữ liệu và output

Profile promotion dùng lại physical corpus đã qualification 1.000 item/500
container của Level 2, giữ nguyên raw checksum và generation manifest. Dữ liệu
processed và run output vẫn được cô lập tại:

```text
data/processed/level_04/
outputs/level_04/runs/<run_id>/
```

Các trường `stackability_code` và `max_stackability` được sử dụng. Những trường
thuộc nesting, delivery, balance hoặc load transfer chỉ được giữ lại nhưng chưa
kích hoạt ở Level 4.

## Validation độc lập

Validator dựng lại support và stack graph từ placements cùng dữ liệu gốc, rồi
kiểm tra orientation, boundary, overlap, payload, exact support, center support,
parent duy nhất, compatibility group, non-stackable policy, cycle và chain cap.

Chỉ run có solver status thành công và validation `VALID` mới có official
objective. Timeout, incomplete hoặc invalid phải có objective `null`.

## Gate promotion inventory

Chạy thủ công sau khi targeted/full tests đạt:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_benchmark.py `
  --suite config\level_04\benchmarks\inventory_promotion_20_500_manual.yaml
```

Gate gồm 20, 100, 300 và 500 item; Best Fit, FFD, MES; hai repeat. Mọi success
phải `VALID`, cùng case phải có cùng fingerprint và hai repeat phải có cùng
objective/placement signature.

## Giới hạn

Level 4 không mô hình hóa load-bearing, load transfer, áp suất, độ bền vật liệu,
center of gravity, fragility, nesting hay thứ tự giao/dỡ. Stackability hợp lệ
không đồng nghĩa nghiệm đã ổn định vật lý khi xe di chuyển.
