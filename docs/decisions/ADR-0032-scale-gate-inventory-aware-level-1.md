# ADR-0032: Scale gate cho tìm kiếm inventory-aware tại Level 1

## Trạng thái

Protocol đã khóa. Gate A catalog 5.000 đã có evidence inspection; Gate B solver
vẫn cần evidence benchmark thủ công trước khi tích hợp inventory-aware search
vào các pipeline Level 2–5.

## Quyết định

Hai profile fleet được dùng để kiểm tra kiến trúc tìm kiếm container:

- `fleet_500_t10`: 500 physical container thuộc 10 type;
- `fleet_5000_t25`: 5.000 physical container thuộc 25 type.

Mỗi physical container có ID duy nhất. Các type variant được sinh tái lập từ catalog gốc, có provenance `source_container_id`, thứ tự variant và hệ số kích thước/tải trọng/chi phí trong generation manifest. Raw catalog không bị sửa.

Gate A chỉ chạy data/inventory inspection: kiểm tra checksum, schema, normalize inventory, hard precheck, lower bound và preview lazy subset. Gate A tuyệt đối không gọi packing solver.

Gate B chạy Best Fit inventory-aware trên Level 1 với catalogue đã sinh. FFD chỉ là comparator. Mọi nghiệm Gate B phải qua independent validator Level 1; timeout hoặc nghiệm không hoàn chỉnh không có official objective.

## Lý do

Không được enumerate power set của 500 hoặc 5.000 physical container. Policy hiện hành chỉ sinh portfolio bounded theo cardinality, sau đó materialize physical IDs khi cần. Các container cùng type vẫn giữ quantity và physical ID riêng để tránh dùng một instance nhiều lần.

## Hệ quả

- `inspect_generated_dataset.py --intent inventory_scale_gate` tạo evidence cô lập dưới `outputs/level_01/runs/`.
- Gate A là evidence về data pipeline/inventory search, không phải evidence packing.
- Chỉ sau khi Gate A và Gate B của Level 1 đạt mới lập task tích hợp vào Level 2, rồi 3, 4 và 5. Các policy support/orientation/stackability/load-bearing hiện có không bị viết lại.

## Giới hạn

Đây là bounded heuristic, không chứng minh đã xét toàn bộ subset. Không dùng profile 100.000 item hoặc 1 triệu item làm solver acceptance trong gate này.
