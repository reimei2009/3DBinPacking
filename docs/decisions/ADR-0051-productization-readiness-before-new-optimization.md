# ADR-0051 — Ưu tiên productization readiness trước tối ưu mới

## Trạng thái

Accepted — 2026-08-21.

## Bối cảnh

Level 1–5 đã có solver, kiểm định độc lập, UI và benchmark nghiên cứu. Tuy nhiên dữ
liệu chi phí, chịu tải, sai số đo và khoảng hở an toàn chưa có nguồn doanh nghiệp.
Contact/support index V1 và V2 đều không đạt ngưỡng cải thiện 20%; vì vậy Cache V3
không có đủ bằng chứng để triển khai.

## Quyết định

1. Giữ corpus 1.000/500 hiện tại làm regression kỹ thuật.
2. Thêm company-like corpus ở lớp `synthetic_calibrated_shadow`; tuyệt đối không gọi
   đây là dữ liệu thật hoặc chứng nhận production.
3. Mọi field phải khai báo `used`, `preserved`, `transformed` hoặc `unsupported` kèm
   provenance.
4. Shadow gate đo VALID, timeout, runtime p50/p95, peak RSS, deterministic và phản
   hồi UI. Kết quả chỉ có thể là `SHADOW_PASS` hoặc `SHADOW_NOT_READY`.
5. Chỉ xem xét cache trở lại nếu profiling mới cho thấy thao tác lặp chiếm ít nhất
   30%, hit-rate dự kiến ít nhất 40% và wall-time có thể giảm ít nhất 20%.
6. Repair early-stop là thử nghiệm A/B opt-in sau khi corpus shadow tồn tại; không
   thay objective hoặc tự bật repair.

## Hệ quả

- Không mở Level 6 và không thêm constructor trong checkpoint này.
- CI phải ép import từ `src` của checkout hiện tại để tránh editable package của
  worktree khác.
- Company-like corpus chưa thay thế corpus canonical kỹ thuật và chưa chứng minh
  an toàn cơ học hay SLA production.
