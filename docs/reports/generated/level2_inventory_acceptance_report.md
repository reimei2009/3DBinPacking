# Nghiệm thu inventory-aware search Level 2

## Phạm vi

Báo cáo này nghiệm thu khả năng tìm container trong catalog vật lý dị thể cho
Level 2, đồng thời giữ nguyên ràng buộc hỗ trợ đáy chính xác và validator độc
lập. Đây là evidence research; không phải chứng nhận ổn định vận tải thực tế.

## Protocol

- Solver: `extreme_point_best_fit` và `extreme_point_ffd`.
- Ràng buộc: geometry, payload, floor/base support, exact union support area và
  base-center support.
- Inventory search: normalization, hard precheck, lower bound, lazy ranked
  subset search; không duyệt power set toàn catalog.
- Objective: ít container, sau đó chi phí. Chỉ `FEASIBLE + VALID` có objective.

## Gate A — 500 container

Nguồn: `outputs/level_02/runs/20260806T095043964660Z__level_02__benchmark__seed42`.

| Profile | Solver | Kết quả | Container dùng | Chi phí | Deterministic |
|---|---:|---|---:|---:|---|
| 20 item / 500 | Best Fit | VALID | 1 | 1.850 | Có, 2 repeat |
| 20 item / 500 | FFD | VALID | 1 | 1.850 | Có, 2 repeat |
| 50 item / 500 | Best Fit | VALID | 2 | 4.000 | Có, 2 repeat |
| 50 item / 500 | FFD | VALID | 2 | 4.000 | Có, 2 repeat |

## Gate B — 5.000 container

Nguồn: `outputs/level_02/runs/20260806T095111715830Z__level_02__benchmark__seed42`.

| Profile | Solver | Kết quả | Container dùng | Chi phí | Runtime trung bình |
|---|---:|---|---:|---:|---:|
| 100 item / 5.000 | Best Fit | VALID | 7 | 9.450 | 19,45 giây |
| 100 item / 5.000 | FFD | VALID | 7 | 9.450 | 17,19 giây |

Hai repeat của mỗi solver có cùng selected-item checksum, input fingerprint,
placement signature và exact-support ratio tối thiểu bằng `1.0`. Revalidation
độc lập cho run Best Fit `20260806T095130734039Z__level_02__extreme_point_best_fit__i100_c5000__seed42`
trả `valid: true`, không có issue.

## Kết luận

Inventory-aware search được promote cho Best Fit và FFD Level 2, bao gồm UI.
MILP, EMS, Hill Climbing và SA không hỗ trợ inventory mode trong checkpoint này;
chúng fail sớm thay vì fallback âm thầm.

## Audit consolidation 100 kiện / kho 500 container

Run kiểm tra ngày 2026-08-06 có tổng khối lượng `26.919,298 kg` và tổng thể tích
`206,3292752 m³`. Container lớn nhất trong catalog có payload `9.250 kg` và thể
tích `77,1375 m³`; vì vậy aggregate lower bound là 3 container. Hai container là
bất khả thi ngay từ capacity bound, dù scene còn khoảng trống nhìn thấy.

Baseline FFD dùng 5 container. Với request khóa đúng `max_used_container_count=5`,
consolidation thử cardinality 3–4 và tìm được nghiệm `VALID` dùng 4 container,
chi phí giảm từ `10.000` xuống `8.000`. Independent revalidation của run
`20260806T110613502695Z__level_02__extreme_point_ffd__i100_c500__seed42` trả
`valid: true`. Khoảng cách 4→3 vẫn là heuristic gap, không phải chứng minh rằng
3 container bất khả thi.

## Gate type-composition và runtime 300 kiện

Checkpoint ngày 2026-08-07 thay physical-subset portfolio bằng search theo thành
phần loại container. Các subset chỉ khác ID của container tương đương không còn
được gửi lặp lại cho constructive solver.

| Request | Kết quả | Container dùng | Runtime | Diễn giải |
|---|---:|---:|---:|---|
| 100 item / kho 500 / max 5 / FFD | VALID | 4 | khoảng 5,4 giây | Giữ gate cũ |
| 300 item / kho 500 / max 15 / Best Fit | VALID | 12 | 13,7–14,6 giây | Hai run deterministic |
| 300 item / kho 500 / max 10 / FFD | TIME_LIMIT | — | khoảng 30 giây | Objective `null`, không chứng minh vô nghiệm |

Hai run Best Fit 300 item có cùng checksum `placements.csv`:
`9323A03C25C2166C155CD75B0FA5BC848BB237C446642C82DB2E73AE28FFD780`.
Independent revalidation của cả gate 100 và gate 300 đều trả `valid: true`, không
có issue. Gate max 10 xác nhận deadline chung hoạt động và diagnostics phân biệt
rõ search timeout với bất khả thi toán học.
