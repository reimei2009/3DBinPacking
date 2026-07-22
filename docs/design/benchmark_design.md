# Benchmark design

The benchmark runner discovers only implemented level/algorithm combinations from the registries. Every matrix case is a normal immutable experiment run with its own inputs, solution, validator, metrics, and manifest. The aggregate is another level-isolated run whose `manifest.json` references all source runs.

`benchmark/results.csv` is the raw comparison table. It includes the effective random seed, timing repeat, quality metrics, and canonical placement signature. `benchmark/summary.csv` and `summary.json` report run/seed counts, success rate, mean/standard deviation/range for primary quality metrics, compactness statistics, runtime, and distinct-solution count. A case succeeds only when its algorithm returns a completed solution status accepted by the level and the independent validator reports valid. `OPTIMAL` and `FEASIBLE` remain distinct.

This contract allows future heuristics to be registered and compared without changing benchmark orchestration.

## Named research corpus

`config/level_01/benchmarks/research_corpus.yaml` defines named cases instead of relying only on a Cartesian count matrix. Each case declares its scale group, difficulty, item/container counts, expected outcome, algorithms, config, and description. A corpus run writes one immutable aggregate under `outputs/level_01/runs/<run_id>/` and every execution remains a normal independently validated experiment run.

Reference selection is explicit:

1. the minimum validated `OPTIMAL` objective is `proven_optimal`;
2. without an optimal run, the minimum validated feasible objective is `best_known`;
3. an exact `INFEASIBLE` result is `proven_infeasible`;
4. otherwise the reference is `unavailable`.

Objective gaps are reported only when a numeric reference exists. `best_known` is not presented as a global optimum. `INFEASIBLE_HEURISTIC` can match the expected behavior of an infeasible regression case, but only exact MILP contributes an infeasibility proof.

Corpus artifacts are `case_catalog.csv`, `results.csv`, `summary.csv`, `ranking.csv`, `references.csv`, and `summary.json`. The manifest records the corpus checksum, every case-config checksum, all source runs, seeds, environment, source commit, and dependency versions.

For stochastic methods, `--seeds 7 11 19` evaluates independent seeded trajectories. `--repeats 2` runs each seed twice to measure timing noise and verify same-seed reproducibility. If `--seeds` is omitted, the runner uses `project.random_seed`, preserving the original single-seed behavior. Duplicate seeds are rejected because repetition belongs in `--repeats`.
