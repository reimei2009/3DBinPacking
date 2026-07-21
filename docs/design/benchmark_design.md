# Benchmark design

The benchmark runner discovers only implemented level/algorithm combinations from the registries. Every matrix case is a normal immutable experiment run with its own inputs, solution, validator, metrics, and manifest. The aggregate is another level-isolated run whose `manifest.json` references all source runs.

`benchmark/results.csv` is the raw comparison table. It includes the effective random seed, timing repeat, quality metrics, and canonical placement signature. `benchmark/summary.csv` and `summary.json` report run/seed counts, success rate, mean/standard deviation/range for primary quality metrics, compactness statistics, runtime, and distinct-solution count. A case succeeds only when its algorithm returns a completed solution status accepted by the level and the independent validator reports valid. `OPTIMAL` and `FEASIBLE` remain distinct.

This contract allows future heuristics to be registered and compared without changing benchmark orchestration.

For stochastic methods, `--seeds 7 11 19` evaluates independent seeded trajectories. `--repeats 2` runs each seed twice to measure timing noise and verify same-seed reproducibility. If `--seeds` is omitted, the runner uses `project.random_seed`, preserving the original single-seed behavior. Duplicate seeds are rejected because repetition belongs in `--repeats`.
