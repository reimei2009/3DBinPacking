# Nghiệm thu Level 2

- Trạng thái: `PASS`
- Gate nội bộ: `PASS`
- Gate MPV: `PASS`
- Cho phép lập kế hoạch promote inventory orchestration sang Level 3: `true`
- Objective chính thức: `(used_container_count, total_container_cost)`.
- Scalar encoded chỉ dùng để đọc artifact legacy.
- MPV được đánh giá với fixed orientation và exact support của Level 2.
- `best_observed` chỉ là nghiệm tốt nhất quan sát được trên cùng input fingerprint trong run này; không phải best-known MPV gốc và không chứng minh tối ưu.

## Evidence

| Nhóm | Rows | Thành công | Deterministic | Objective invariant | Telemetry | Runtime lớn nhất (s) | Peak RSS (bytes) |
|---|---:|---:|---|---|---|---:|---:|
| fleet_500 | 8 | 8 | True | True | True | 0.197 | 176660480 |
| fleet_5000 | 4 | 4 | True | True | True | 22.311 | 188227584 |
| scale_20_300 | 12 | 12 | True | True | True | 13.195 | 201592832 |
| mpv_fixed_orientation | 108 | 108 | True | True | True | 0.502 | 211070976 |

## Kiểm tra protocol MPV

- `execution_count_108`: `PASS`
- `successful_and_independently_valid`: `PASS`
- `case_count_27`: `PASS`
- `algorithms_best_fit_and_ffd`: `PASS`
- `two_repeats_per_case_algorithm`: `PASS`
- `deterministic_signature_and_objective`: `PASS`
- `objective_null_on_failure`: `PASS`
- `one_fingerprint_per_case`: `PASS`
- `one_item_checksum_per_case`: `PASS`
- `dataset_family_is_mpv`: `PASS`
- `telemetry_peak_memory_and_termination_complete`: `PASS`
- `canonical_best_observed_reference`: `PASS`
- `no_legacy_reference_kind`: `PASS`
- `best_fit_pairwise_outcomes_1_25_1`: `PASS`
