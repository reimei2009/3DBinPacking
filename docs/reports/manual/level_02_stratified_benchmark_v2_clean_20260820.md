# Benchmark Level 2 V2 phân tầng

- Functional gate: `PASS`
- Provenance gate: `PASS`
- Quyết định governance: `CANONICAL_PROMOTION_ALLOWED`
- Tổng số bài: 84
- Tổng lượt chạy: 756

Ba tầng được báo riêng; stress và prefix không tham gia kết luận phân phối random.

## Gate từng tầng

- `random_distribution`: functional PASS, provenance PASS — 60 bài, 540 lượt, commit `37bd873e0df789e936505606787d1adcb8b675ab`, git_dirty=`False`.
- `stress`: functional PASS, provenance PASS — 18 bài, 162 lượt, commit `37bd873e0df789e936505606787d1adcb8b675ab`, git_dirty=`False`.
- `prefix_regression`: functional PASS, provenance PASS — 6 bài, 54 lượt, commit `37bd873e0df789e936505606787d1adcb8b675ab`, git_dirty=`False`.

## So sánh trên phân phối random

- `extreme_point_ffd`: 3 thắng / 57 hòa / 0 thua so với Best Fit.
- `maximal_space_best_fit`: 6 thắng / 53 hòa / 1 thua so với Best Fit.

## Diễn giải governance

V2 đã đạt cả functional và provenance gate. Ba source run cùng commit, đều `git_dirty=false`, và toàn bộ checksum gate đạt; V2 đủ điều kiện canonical còn V1 chuyển sang evidence lịch sử `superseded`.

`proven_optimal` chỉ dành cho exact proof; `best_observed` chỉ là nghiệm tốt nhất trên cùng input fingerprint; aggregate lower bound chỉ là cận capacity sơ bộ.
