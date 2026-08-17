# Contact/Support Index V1 — Kết quả A/B ngày 2026-08-17

Trạng thái: **NOT PROMOTED**.

V1 chứng minh index không làm thay đổi tính đúng đắn: mỗi Level có 108/108 lượt
`VALID`; 18/18 cặp giữ nguyên status, official objective, placement signature
và rejection counters. Independent validator vẫn dùng brute force.

| Level | Construction trung vị | Wall speedup trung vị | Cặp construction fail | Cặp wall fail |
| --- | ---: | ---: | ---: | ---: |
| Level 4 | +6,92% | 1,089× | 3/18 | 4/18 |
| Level 5 | −1,11% | 0,981× | 6/18 | 11/18 |

Gate yêu cầu construction cải thiện ít nhất 20%, wall runtime không regression
và không constructor nào regression construction quá 5%. Cả hai Level đều
không đạt, vì vậy index V1 tiếp tục mặc định tắt.

Nguồn diagnostic:

- Level 4: `20260817T040619737881Z__level_04__benchmark_corpus__level_04_contact_support_index_ab_v1__seed42`;
- Level 5: `20260817T050431203215Z__level_05__benchmark_corpus__level_05_contact_support_index_ab_v1__seed42`.

Hai manifest ghi commit `0b7ce6e` nhưng có `git_dirty=true`, nên evidence này
chỉ dùng định hướng V2, không được coi là release evidence hoặc đưa vào ranking
canonical.

Quyết định tiếp theo: cho phép đúng một vòng V2 để giảm query lặp và allocation
trong broad phase. Nếu V2 không đạt toàn bộ gate ở cả Level 4 và Level 5, dự án
dừng hướng này ở trạng thái research comparator và không mở V3.
