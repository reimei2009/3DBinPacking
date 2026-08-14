# Acceptance phân phối và profiling Level 3–5 — 2026-08-14

- Trạng thái: `PASS`
- Phạm vi: 84 bài và 756 lượt chạy cho mỗi Level; tổng cộng 2.268 lượt.
- Chỉ so sánh thuật toán trong cùng Level. Chênh lệch giữa các Level chỉ mô tả chi phí của ràng buộc.
- Best Fit là mốc đối chiếu, không phải nghiệm tối ưu đã chứng minh.

## Gate và chất lượng trên 60 bài random

### level_03: PASS — 84 bài / 756 lượt

- `extreme_point_ffd` so với Best Fit: 1 thắng / 59 hòa / 0 thua.
- `maximal_space_best_fit` so với Best Fit: 18 thắng / 38 hòa / 4 thua.

### level_04: PASS — 84 bài / 756 lượt

- `extreme_point_ffd` so với Best Fit: 1 thắng / 57 hòa / 2 thua.
- `maximal_space_best_fit` so với Best Fit: 32 thắng / 28 hòa / 0 thua.
- Recovery bất biến: tái sử dụng 747 lượt VALID và chạy lại 9 lượt lỗi kỹ thuật.

### level_05: PASS — 84 bài / 756 lượt

- `extreme_point_ffd` so với Best Fit: 2 thắng / 57 hòa / 1 thua.
- `maximal_space_best_fit` so với Best Fit: 32 thắng / 28 hòa / 0 thua.
- Recovery bất biến: tái sử dụng 161 lượt VALID và chạy lại 1 lượt lỗi kỹ thuật.

## Chi phí runtime của ràng buộc

- Level 4 / Level 3: trung vị `1.028×` trên cùng bài và thuật toán.
- Level 5 / Level 4: trung vị `1.473×` trên cùng bài và thuật toán.

Các tỷ lệ này mô tả overhead của stackability và load-bearing; không xếp hạng Level nào tốt hơn.

## Profiling và quyết định kỹ thuật

### level_03

- Construction: `59.6%` wall time; reporting: `15.5%`.
- Nhóm kiểm tra vật lý: `18.7%` profiled solver self-time.
- Candidate enumeration `20.4%`; overlap `14.5%`; exact support `4.2%`; stackability `0.0%`; load transfer `0.0%`.
- Ưu tiên theo gate: `construction_requires_deeper_measurement`.

### level_04

- Construction: `70.9%` wall time; reporting: `11.0%`.
- Nhóm kiểm tra vật lý: `54.6%` profiled solver self-time.
- Candidate enumeration `11.3%`; overlap `7.8%`; exact support `37.9%`; stackability `8.9%`; load transfer `0.0%`.
- Ưu tiên theo gate: `spatial_or_contact_index`.

### level_05

- Construction: `71.6%` wall time; reporting: `10.1%`.
- Nhóm kiểm tra vật lý: `58.7%` profiled solver self-time.
- Candidate enumeration `10.2%`; overlap `7.2%`; exact support `39.6%`; stackability `9.0%`; load transfer `2.9%`.
- Ưu tiên theo gate: `spatial_or_contact_index`.

## Kết luận

Level 3 chưa có một nhóm hàm đơn lẻ vượt ngưỡng 40%, nên chưa tối ưu vi mô.
Level 4–5 bị chi phối bởi construction và các phép kiểm tra tiếp xúc/support; bước kỹ thuật tiếp theo là thiết kế A/B cache hoặc contact index dùng chung, giữ nguyên behavior khi tắt.
MES có tín hiệu chất lượng rõ ở Level 4–5 trên phân phối random, nên có thể mở A/B promotion riêng sau khi xử lý hoặc chấp nhận runtime budget.
Level 6 tiếp tục đóng băng.

Lưu ý: cProfile tạo overhead. Runtime chính thức luôn lấy từ benchmark không profile; profile chỉ dùng xác định hotspot.
