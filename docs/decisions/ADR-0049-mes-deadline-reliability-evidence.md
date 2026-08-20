# ADR-0049 — Evidence độ tin cậy deadline MES

## Trạng thái

Investigation complete — `NO_COOPERATIVE_HARDENING_REQUIRED`, 2026-08-20.

## Bối cảnh

Một lượt MES Level 5 từng vượt deadline khoảng 17 phút nhưng vẫn giữ incumbent hợp lệ.
Windows System log cho thấy máy đi vào Modern Standby đúng trong khoảng này. Chỉ nhìn
`perf_counter` không thể phân biệt sleep, tranh chấp CPU và operation MES không thể ngắt.
Portfolio V1 vẫn là `NOT_PROMOTED`; quyết định này không diễn giải lại artifact cũ.

## Quyết định

- Deadline tiếp tục dùng wall-clock nghiêm ngặt; sleep vẫn tính vào deadline.
- Observer chỉ đo wall clock, performance clock, process CPU time và trên Windows là
  `QueryUnbiasedInterruptTime` (active time không gồm Modern Standby).
- MES ghi checkpoint quanh candidate, feasibility, exact support, stackability, load
  transfer, scoring và cập nhật/pruning maximal spaces.
- Observer không gia hạn deadline, không đổi status, objective, placement hoặc validator.
- Phân loại gồm `NORMAL`, `SYSTEM_SUSPEND_DETECTED`, `HOST_CONTENTION_SUSPECTED`,
  `CLOCK_DISCONTINUITY` và `LONG_NON_INTERRUPTIBLE_OPERATION`.
- Run nhiễu môi trường được giữ nguyên nhưng không đủ điều kiện acceptance.
- Chỉ mở hardening khi active-time operation vượt 1 giây hoặc overshoot sạch vượt
  `max(1 giây, 1% deadline)`.
- Evidence chính thức gồm 18/18 lượt `FEASIBLE + VALID`, 6 nhóm deterministic,
  không có execution nhiễu môi trường và không có deadline overshoot.
- Operation dài nhất là `exact_support`, khoảng 0,01093 giây. Không mở cooperative
  hardening và không dùng subprocess watchdog.

## Hệ quả và giới hạn

Telemetry mặc định tắt và chỉ bật trong suite diagnostic. Các run diagnostic không tham
gia canonical ranking. Independent validator tiếp tục chạy đường riêng không dùng
observer. Portable fallback không thể tách Modern Standby chi tiết như Windows.
Portfolio V1 tiếp tục `NOT_PROMOTED`; evidence mới không đảo ngược gate runtime và
deterministic Level 5. MES tiếp tục là research comparator và Level 6 tiếp tục đóng băng.

Report đã khóa checksum và provenance tại
[MES deadline reliability ngày 2026-08-20](../reports/manual/mes_deadline_reliability_20260820.md).
