# Tiêu chí nghiệm thu Level 2

Level 2 chỉ được xem là đóng khi đồng thời thỏa các điều kiện sau:

- toàn bộ regression Level 1 pass và output Level 1/2 vẫn cô lập;
- mọi nghiệm thành công complete, independently `VALID` và có official
  objective `(used_container_count, total_container_cost)`;
- timeout, incomplete hoặc invalid có official objective `null`;
- exact union support ratio đạt threshold và base center được hỗ trợ;
- repair/consolidation không thể làm mất validated incumbent;
- hai repeat cùng input/seed có cùng placement signature và objective;
- gate inventory 20–300 items, fleet 500 và fleet 5.000 container đạt;
- corpus MPV fixed-orientation có đúng 27 case, Best Fit/FFD, hai repeat và 108
  execution; mọi execution thành công và independently `VALID`;
- mỗi case có đúng một input fingerprint và item checksum; mỗi cặp case–algorithm
  deterministic về placement signature và official objective;
- reference heuristic dùng `best_observed`, không so với best-known semantics gốc;
- evidence machine-readable ghi runtime từng phase, peak memory, checksum,
  acquisition ladder và termination reason.

`support.csv` và `support_validation.json` phải được lưu mà không thay schema
placement. Manifest phải ghi support đang hoạt động; rotation, stackability,
load-bearing, load transfer và ổn định vật lý đầy đủ vẫn không hoạt động.

Nhãn `best_observed` chỉ có nghĩa là objective tốt nhất trong đúng input fingerprint
của run acceptance; nó không phải best-known MPV gốc và không chứng minh tối ưu.
Artifact cũ có `best_known` vẫn đọc được như legacy nhưng không đủ để phát hành
evidence acceptance mới.

Nếu chưa có bundle MPV local cùng checksum tin cậy, acceptance phải trả
`BLOCKED_EXTERNAL_CORPUS`; không được âm thầm bỏ gate hoặc cho phép lập kế hoạch
promote inventory orchestration sang Level 3. Runtime Level 3 hiện hữu không bị
thay đổi bởi checkpoint này.
