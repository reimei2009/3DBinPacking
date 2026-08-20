# Benchmark Level 2 V2 phân tầng

- Functional gate: `PASS`
- Provenance gate: `FAIL`
- Quyết định governance: `CANONICAL_PENDING_CLEAN_RERUN`
- Tổng số bài: 84
- Tổng lượt chạy: 756

Ba tầng được báo riêng; stress và prefix không tham gia kết luận phân phối random.

## Gate từng tầng

- `random_distribution`: functional PASS, provenance FAIL — 60 bài, 540 lượt, commit `86e36b4552dccbcee07f5b5a585795637c4f9645`, git_dirty=`True`.
  - source run có git_dirty=true hoặc không khai báo sạch
- `stress`: functional PASS, provenance FAIL — 18 bài, 162 lượt, commit `86e36b4552dccbcee07f5b5a585795637c4f9645`, git_dirty=`True`.
  - source run có git_dirty=true hoặc không khai báo sạch
- `prefix_regression`: functional PASS, provenance FAIL — 6 bài, 54 lượt, commit `86e36b4552dccbcee07f5b5a585795637c4f9645`, git_dirty=`True`.
  - source run có git_dirty=true hoặc không khai báo sạch

## So sánh trên phân phối random

- `extreme_point_ffd`: 3 thắng / 57 hòa / 0 thua so với Best Fit.
- `maximal_space_best_fit`: 6 thắng / 53 hòa / 1 thua so với Best Fit.

## Diễn giải governance

V2 đã đạt gate chức năng nhưng chưa thay V1 vì các source run hiện tại được tạo khi working tree còn thay đổi. V1 tiếp tục là canonical; V2 giữ vai trò research candidate cho đến khi chạy lại sạch và toàn bộ checksum gate đạt.

`proven_optimal` chỉ dành cho exact proof; `best_observed` chỉ là nghiệm tốt nhất trên cùng input fingerprint; aggregate lower bound chỉ là cận capacity sơ bộ.

## Clean rerun bắt buộc trước promotion

```powershell
.\.venv\Scripts\python.exe .\scripts\run_benchmark_corpus.py `
  --corpus config\level_02\benchmarks\generated_1k_500_random_candidate.yaml

.\.venv\Scripts\python.exe .\scripts\run_benchmark_corpus.py `
  --corpus config\level_02\benchmarks\generated_1k_500_stress_candidate.yaml

.\.venv\Scripts\python.exe .\scripts\run_benchmark_corpus.py `
  --corpus config\level_02\benchmarks\generated_1k_500_prefix_regression.yaml
```
