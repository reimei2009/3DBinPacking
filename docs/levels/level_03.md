# Level 3 — Xoay ngang và hỗ trợ hình học

Trạng thái: **nghiên cứu đã nghiệm thu; inventory search đã được mở trên CLI,
benchmark và Streamlit**.

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

Level này chưa kích hoạt vertical rotation, stackability, load-bearing,
nesting, fragility, center of gravity hoặc loading/unloading order. Exact
geometric support không phải chứng nhận ổn định vật lý đầy đủ.

## Inventory-aware workflow

Best Fit, FFD và Maximal Empty Spaces dùng chung `InventoryLevelAdapter` và
`InventorySearchOrchestrator` với Level 1–2. Level 3 compose thêm horizontal
orientation provider, exact-support policy, support closure và independent
candidate validator riêng.

Nguồn Streamlit mặc định là corpus đã qualification gồm 1.000 kiện và 500
physical container thuộc 10 loại. Người dùng được chọn tự do số kiện, số
container bắt đầu tìm và giới hạn container tối đa trong phạm vi nguồn. Chạy
đơn, benchmark tùy chỉnh, precheck và lịch sử đều dùng cùng active profile.

Hill Climbing, Simulated Annealing và MILP chưa hỗ trợ inventory orchestration.
Khi dùng catalog cơ bản không-inventory, các thuật toán này vẫn có thể được
chọn. Khi dùng nguồn inventory 1.000/500, UI chỉ hiển thị Best Fit, FFD và MES;
không fallback sang catalog khác.

Repair Level 3 vẫn mặc định tắt và chưa được expose trên Streamlit. Checkpoint
UI hiện tại chỉ mở construction inventory đã qua acceptance; final independent
validation luôn được giữ nguyên.

## Objective và bằng chứng

Official objective là `(số container đã dùng, tổng chi phí container)`.
Nghiệm incomplete, timeout hoặc invalid không có official objective.

Acceptance phân phối dùng 84 bài và 756 lượt trên cùng nguồn 1.000/500:

- 756/756 lượt independently `VALID`;
- 252/252 nhóm case–algorithm deterministic;
- random, stress và prefix regression được báo cáo riêng;
- Best Fit chỉ là baseline đối chiếu, không phải optimum đã chứng minh.

Evidence canonical nằm tại
`docs/reports/manual/level_03_05_distribution_20260814/`.

## Cô lập dữ liệu và output

Raw/generated provenance của corpus được tái sử dụng, nhưng processed data và
mọi run Level 3 chỉ được ghi vào:

```text
data/processed/level_03/
outputs/level_03/runs/<run_id>/
```

Raw field `forced_orientation` được bảo toàn nhưng chưa có mapping semantics đã
xác minh. Solver dùng profile tường minh `horizontal_rotatable`, không suy đoán
orientation từ field này.
