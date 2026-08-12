# ADR-0043 — Benchmark canonical Level 2

## Trạng thái

Accepted — 2026-08-12.

## Quyết định

Benchmark nội bộ Level 2 dùng một nguồn canonical 1.000 item / 500 container / 10
loại. Protocol constructor có 24 case ở sáu quy mô và dùng Extreme Point Best Fit
làm baseline. Repair được đánh giá bằng protocol A/B riêng; MPV là evidence học
thuật độc lập.

Benchmark chuẩn bất biến. UI có thể chạy bản quick hoặc tạo phép so sánh tùy
chỉnh, nhưng kết quả tùy chỉnh không được nhập vào kết luận canonical.

## Lý do

Một case đơn lẻ không đại diện cho chất lượng tổng thể. Gộp các dataset, container
catalog hoặc semantics khác nhau cũng tạo kết luận sai. Việc khóa input fingerprint,
container limits và deadline cho phép đánh giá công bằng, tái lập được.

## Hệ quả

- Constructor, repair và MPV có báo cáo tách biệt.
- p50/p95 chỉ có ý nghĩa trên nhiều execution cùng strata quy mô.
- 750/1.000 item là scale gate thủ công, không làm UI bị khóa mặc định.
- Config cũ được phân loại trong registry; xóa chỉ sau cleanup audit được duyệt.
