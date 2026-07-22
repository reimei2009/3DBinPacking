# Benchmark design

The benchmark runner discovers only implemented level/algorithm combinations from the registries. Every matrix case is a normal immutable experiment run with its own inputs, solution, validator, metrics, and manifest. The aggregate is another level-isolated run whose `manifest.json` references all source runs.

`benchmark/results.csv` is the raw comparison table. It includes the effective random seed, timing repeat, quality metrics, and canonical placement signature. `benchmark/summary.csv` and `summary.json` report run/seed counts, success rate, mean/standard deviation/range for primary quality metrics, compactness statistics, runtime, and distinct-solution count. A case succeeds only when its algorithm returns a completed solution status accepted by the level and the independent validator reports valid. `OPTIMAL` and `FEASIBLE` remain distinct.

This contract allows future heuristics to be registered and compared without changing benchmark orchestration.

## Corpus nghiên cứu có định danh

`config/level_01/benchmarks/research_corpus.yaml` định nghĩa các case có tên thay vì chỉ dùng tích Descartes giữa số item và container. Mỗi case khai báo nhóm quy mô, độ khó, số item/container, kết quả kỳ vọng, thuật toán, config và mô tả. Một lần chạy ghi aggregate bất biến dưới `outputs/level_01/runs/<run_id>/`; từng source run vẫn là experiment được independent validator kiểm tra.

Quy tắc chọn reference:

1. objective nhỏ nhất trong nghiệm `OPTIMAL` hợp lệ là `proven_optimal`;
2. nếu không có optimal, objective nhỏ nhất trong nghiệm khả thi hợp lệ là `best_known`;
3. exact `INFEASIBLE` tạo reference `proven_infeasible`;
4. trường hợp còn lại là `unavailable`.

Objective gap chỉ được báo khi có numeric reference. `best_known` không được trình bày như global optimum. `INFEASIBLE_HEURISTIC` có thể khớp expected behavior của regression case, nhưng chỉ exact MILP tạo chứng minh bất khả thi.

Artifact gồm `case_catalog.csv`, `results.csv`, `summary.csv`, `ranking.csv`, `references.csv` và `summary.json`. Manifest ghi checksum corpus/config, source runs, seed, environment, source commit và dependency versions.

For stochastic methods, `--seeds 7 11 19` evaluates independent seeded trajectories. `--repeats 2` runs each seed twice to measure timing noise and verify same-seed reproducibility. If `--seeds` is omitted, the runner uses `project.random_seed`, preserving the original single-seed behavior. Duplicate seeds are rejected because repetition belongs in `--repeats`.
