# Level 1 — Xếp kiện hình hộp với hướng cố định

## Mục tiêu và phạm vi

Level 1 xếp toàn bộ kiện hình hộp chữ nhật vào các physical container dị thể.
Mỗi kiện giữ orientation cố định. Mục tiêu được so sánh theo thứ tự:

1. ít container được sử dụng hơn;
2. tổng chi phí thực nghiệm thấp hơn.

Các ràng buộc đang hoạt động gồm biên container, không chồng lấn, payload và mỗi
kiện xuất hiện đúng một lần. Support, stability, rotation, stackability,
load-bearing, nesting, trọng tâm và thứ tự giao hàng chưa thuộc Level 1.

## Chế độ tìm kiếm container trong inventory

`container_search` là chế độ opt-in, hiện chỉ hỗ trợ
`extreme_point_best_fit` và `extreme_point_ffd`.

Khi tắt, `instance.container_count` giữ nguyên semantics legacy: chuẩn bị prefix
container có kích thước tương ứng.

Khi bật:

- toàn bộ catalog được đọc làm inventory;
- `initial_used_container_count` là cardinality bắt đầu tìm kiếm;
- `max_used_container_count` là giới hạn cardinality;
- chỉ tăng cardinality khi `automatically_increase_container_count=true`;
- hard precheck và lower bound volume/payload được tính trước construction;
- subset được duyệt theo cardinality, sau đó ưu tiên chi phí thấp;
- catalog lớn dùng candidate portfolio có giới hạn và deadline.

Ví dụ strict một container:

```yaml
container_search:
  enabled: true
  initial_used_container_count: 1
  max_used_container_count: 1
  automatically_increase_container_count: false
```

Cấu hình trên có nghĩa solver tìm một container phù hợp trong toàn catalog, không
phải mặc định lấy container đầu tiên.

## Validation và trạng thái thất bại

Hard precheck chỉ kết luận các lỗi chắc chắn từ input/capacity. Một
`INFEASIBLE_HEURISTIC` chỉ có nghĩa heuristic chưa tìm được nghiệm trong phạm vi
subset/budget đã cấp; nó không chứng minh bài toán vô nghiệm.

Official objective chỉ có ý nghĩa khi construction complete và independent
validator trả `VALID`. Diagnostic gồm lower bound, subset đã xét, candidate bị
loại, best partial và `unpacked_items` khi có.

## Giới hạn

- Chế độ inventory-aware chưa được bật mặc định.
- MILP, EMS, Hill Climbing và Simulated Annealing chưa dùng contract này.
- Nhánh catalog lớn là bounded heuristic, không chứng minh đã duyệt toàn bộ subset.
- Không được gọi nghiệm Level 1 là phương án ổn định vật lý.
