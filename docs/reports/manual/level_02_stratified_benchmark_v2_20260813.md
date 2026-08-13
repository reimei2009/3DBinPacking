# Benchmark Level 2 V2 phân tầng

- Trạng thái: `PASS`
- Tổng số bài: 84
- Tổng lượt chạy: 756

Ba tầng được báo riêng; stress và prefix không tham gia kết luận phân phối random.

## Gate từng tầng

- `random_distribution`: PASS — 60 bài, 540 lượt.
- `stress`: PASS — 18 bài, 162 lượt.
- `prefix_regression`: PASS — 6 bài, 54 lượt.

## So sánh trên phân phối random

- `extreme_point_ffd`: 3 thắng / 57 hòa / 0 thua so với Best Fit.
- `maximal_space_best_fit`: 6 thắng / 53 hòa / 1 thua so với Best Fit.
