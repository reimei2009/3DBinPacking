# Evidence benchmark canonical Level 2 — 2026-08-13

- Trạng thái: **PASS**.
- Phạm vi: **24 bài kiểm tra**, **144 lượt chạy**.
- Hợp lệ độc lập: **144/144**.
- Nhóm lặp deterministic: **72/72**.
- Mốc đối chiếu: **Extreme Point Best Fit**; đây không phải nghiệm tối ưu đã chứng minh.

## Kết luận chất lượng

FFD hòa Best Fit trên toàn bộ 24 bài; MES có kết quả hỗn hợp với 1 thắng, 22 hòa và 1 thua. Chưa có thuật toán dẫn đầu về chất lượng.

| Thuật toán so với Best Fit | Thắng | Hòa | Thua |
|---|---:|---:|---:|
| Extreme Point FFD | 0 | 24 | 0 |
| Maximal Empty Spaces Best Fit | 1 | 22 | 1 |

## Các bài tạo khác biệt

Chỉ các bài mà ít nhất hai thuật toán dùng số container hoặc chi phí khác nhau mới xuất hiện dưới đây.

| Bài kiểm tra | Số kiện | Thuật toán | Container | Chi phí |
|---|---:|---|---:|---:|
| generated_random303_i100 | 100 | Maximal Empty Spaces Best Fit | 4 | 8000 |
| generated_random303_i100 | 100 | Extreme Point Best Fit | 5 | 10000 |
| generated_random303_i100 | 100 | Extreme Point FFD | 5 | 10000 |
| generated_random303_i500 | 500 | Extreme Point Best Fit | 19 | 38000 |
| generated_random303_i500 | 500 | Extreme Point FFD | 19 | 38000 |
| generated_random303_i500 | 500 | Maximal Empty Spaces Best Fit | 20 | 40000 |

## Chất lượng theo quy mô

Median và min–max dưới đây được tính giữa các bài cùng quy mô, không lấy trung bình raw xuyên quy mô.

| Thuật toán | Số kiện | Gap median | Gap min–max | Wall runtime median (s) |
|---|---:|---:|---:|---:|
| Extreme Point Best Fit | 20 | 0.0 | 0.0–0.0 | 3.555 |
| Extreme Point FFD | 20 | 0.0 | 0.0–0.0 | 3.059 |
| Maximal Empty Spaces Best Fit | 20 | 0.0 | 0.0–0.0 | 3.094 |
| Extreme Point Best Fit | 50 | 0.0 | 0.0–0.0 | 3.317 |
| Extreme Point FFD | 50 | 0.0 | 0.0–0.0 | 3.273 |
| Maximal Empty Spaces Best Fit | 50 | 0.0 | 0.0–0.0 | 3.271 |
| Extreme Point Best Fit | 100 | 1.0 | 0.0–2.0 | 3.771 |
| Extreme Point FFD | 100 | 1.0 | 0.0–2.0 | 3.910 |
| Maximal Empty Spaces Best Fit | 100 | 1.0 | 0.0–1.0 | 3.157 |
| Extreme Point Best Fit | 200 | 2.0 | 1.0–2.0 | 4.449 |
| Extreme Point FFD | 200 | 2.0 | 1.0–2.0 | 3.999 |
| Maximal Empty Spaces Best Fit | 200 | 2.0 | 1.0–2.0 | 4.113 |
| Extreme Point Best Fit | 300 | 3.0 | 3.0–3.0 | 4.859 |
| Extreme Point FFD | 300 | 3.0 | 3.0–3.0 | 4.729 |
| Maximal Empty Spaces Best Fit | 300 | 3.0 | 3.0–3.0 | 4.141 |
| Extreme Point Best Fit | 500 | 5.5 | 5.0–6.0 | 8.840 |
| Extreme Point FFD | 500 | 5.5 | 5.0–6.0 | 8.519 |
| Maximal Empty Spaces Best Fit | 500 | 6.0 | 5.0–6.0 | 6.445 |

## Giới hạn diễn giải

- Best Fit là mốc đối chiếu, không phải nghiệm tối ưu đã được chứng minh.
- Aggregate lower bound chỉ xét sức chứa tổng hợp, không chứng minh khả thi hình học.
- Không lấy trung bình raw container, chi phí hoặc objective giữa các quy mô.
- Mỗi nhóm thuật toán–quy mô có 8 lượt chạy nên chưa công bố p95.

## Kiểm tra phát hành

- `canonical_corpus_id`: **PASS**
- `manifest_status_success`: **PASS**
- `case_count_24`: **PASS**
- `algorithms_exactly_three`: **PASS**
- `execution_count_144`: **PASS**
- `manifest_counts_match`: **PASS**
- `all_success_and_independently_valid`: **PASS**
- `one_fingerprint_per_case`: **PASS**
- `one_item_checksum_per_case`: **PASS**
- `repeat_count_two_for_72_groups`: **PASS**
- `deterministic_objective_and_placement`: **PASS**
- `objective_null_on_failure`: **PASS**
- `ffd_vs_best_fit_0_24_0`: **PASS**
- `mes_vs_best_fit_1_22_1`: **PASS**
