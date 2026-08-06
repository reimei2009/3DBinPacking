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

## Comparator EP–FFD Gap Fill

`extreme_point_ffd_gap_fill` là comparator nghiên cứu CLI/benchmark, không thay
thế EP–FFD chuẩn và không xuất hiện trên Streamlit. Fixture ngữ nghĩa xác nhận
look-ahead insertion có thể lấp một khe cục bộ, nhưng tổng hợp 21 profile thực
và generated cho kết quả `0 WIN / 21 TIE / 2 LOSS`. Vì vậy comparator có trạng
thái `NOT_PROMOTED`, chưa được tích hợp inventory-aware search hoặc port sang
level sau. Xem báo cáo
`docs/reports/manual/level_01_ep_ffd_gap_fill_baseline_20260805.md`.

## UI catalog inventory

Với `extreme_point_best_fit` hoặc `extreme_point_ffd`, Streamlit cho phép chọn
catalog 5, 500/10 type hoặc 5.000/25 type. Catalog 500 và 5.000 là dữ liệu
sinh tái lập dưới `data/interim/synthetic/`; nếu chưa được sinh, UI dừng an
toàn và hiển thị lệnh generate thay vì quay về catalog 5 container.

UI phân biệt ba đại lượng:

- quy mô kho vật lý (`container_inventory_count`);
- số container bắt đầu xét (`initial_used_container_count`);
- số container tối đa được phép dùng (`max_used_container_count`).

Giới hạn tối đa là budget, không phải một prefix catalog. Solver chỉ tìm trong
portfolio subset hữu hạn nên không chứng minh đã duyệt mọi tổ hợp
\(\binom{5000}{m}\). `actual used-container count` có thể thấp hơn cardinality
subset đang xét và luôn phải nhỏ hơn hoặc bằng giới hạn đã cấu hình.

UI hiển thị cả nhãn loại do dữ liệu nguồn khai báo (ví dụ `BOX-A`) và type tương
đương canonical (`CT-...`) dùng nội bộ cho grouping. `inventory_fingerprint` được
ghi vào metadata/manifest để đối chiếu đúng kho physical giữa các lần chạy.

## Giới hạn

- Chế độ inventory-aware chưa được bật mặc định.
- MILP, EMS, Hill Climbing và Simulated Annealing chưa dùng contract này.
- Nhánh catalog lớn là bounded heuristic, không chứng minh đã duyệt toàn bộ subset.
- Không được gọi nghiệm Level 1 là phương án ổn định vật lý.

## Scale gate inventory-aware

Trước khi inventory-aware search được tích hợp vào pipeline Level 2–5, Level 1
phải đạt Gate A và Gate B với fleet 500/10 type và 5.000/25 type. Gate A chỉ
kiểm tra normalize inventory, precheck, lower bound và lazy subset preview;
không gọi solver. Gate B dùng Best Fit là phương pháp chính, FFD là comparator,
và chỉ công nhận objective khi independent validator Level 1 trả `VALID`.
Protocol và lệnh nghiệm thu nằm tại
`docs/reports/manual/level_01_inventory_scale_gate_protocol.md`; chưa promote
sang Level 2 trước khi Gate B có evidence benchmark thủ công.
