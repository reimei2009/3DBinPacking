# Level 1 acceptance report

Generated 2026-07-21 in the project virtual environment.

## Environment

- Python 3.14.4 (the available local interpreter; project supports Python 3.11+)
- NumPy 2.5.1
- SciPy 1.18.0 / HiGHS via `scipy.optimize.milp`
- pandas 2.3.3

## Reproducibility and tests

- Data preparation: 20 items, 5 containers, 24.210313 m3, 6228.728 kg.
- Model: 5865 variables, 18475 constraints, CSR sparse matrix, 48505 nonzero coefficients.
- Pytest: 58 passed, 0 failed.
- Clean and executed notebooks pass `nbformat.validate`; executed notebook prints `VALID LEVEL-1 SOLUTION`.

## Solver and independent validation

- Status: OPTIMAL (HiGHS Status 7)
- Objective: 10992.0
- Selected containers: C2, C4
- Container count: 2
- Synthetic cost: 1810.0
- Placed items: 20/20
- Independent validation: valid, 0 issues

The solution has no boundary, overlap, payload, identity, dimension, or weight violations. Physical support/stability is intentionally not evaluated at Level 1.

## Exact, greedy, local-search, and metaheuristic benchmark

- Algorithms: `milp_big_m`, `extreme_point_ffd`, `extreme_point_hill_climbing`, `extreme_point_simulated_annealing`.
- Matrix: item counts 10/20, container counts 3/5, one repeat.
- Cases: 16; successful and independently validated: 16.
- Aggregate run: `outputs/level_01/runs/20260721T072057247922Z__level_01__benchmark__seed42`.
- On all four tested instances all three non-exact algorithms matched MILP container count, cost, and objective, while correctly reporting FEASIBLE rather than OPTIMAL.
- For 20 items/5 containers: MILP 5.472 seconds; FFD 0.000530 seconds; Hill Climbing 0.011579 seconds; Simulated Annealing 0.132294 seconds (algorithm runtime only).

## Simulated Annealing acceptance evidence

- Standalone run: `outputs/level_01/runs/20260721T072036430280Z__level_01__extreme_point_simulated_annealing__i20_c5__seed42`.
- Status: FEASIBLE; independent validation: valid, 0 issues.
- Used containers: C2+C4; cost 1810; objective 10992.
- Completed 200 iterations, accepted 193 moves including 53 worse-energy moves, demonstrating that the search can leave a Hill-Climbing local state and cool toward selective acceptance.
- Best lexicographic score improved only the occupied bounding-volume tie-breaker on this instance; container count and cost were already optimal.

## Multi-seed robustness benchmark

- Algorithms: `extreme_point_ffd`, `extreme_point_hill_climbing`, `extreme_point_simulated_annealing`.
- Instance: 20 items, 5 containers; seeds 7/11/19; two repeats per seed.
- Cases: 18; successful and independently validated: 18.
- Aggregate run: `outputs/level_01/runs/20260721T073308114299Z__level_01__benchmark__seeds3_10be15e3`.
- Same-seed repeats produced identical placement signatures for every algorithm and seed.
- FFD and Hill Climbing produced one distinct geometry across all seeds; Simulated Annealing produced three.
- All algorithms retained objective 10992, two containers, and cost 1810 on every run.
- Simulated Annealing occupied bounding volume: mean 33,883,686,666.67 mm3, cross-seed standard deviation 327,068,927.50 mm3.

## Simulated Annealing parameter sweep

- Grid: initial temperature 0.05/0.25/1.0; cooling rate 0.95/0.97/0.99; iterations 100/200.
- Parameter sets: 18; seeds 7/11/19; cases 54.
- Successful and independently validated: 54/54.
- Aggregate run: `outputs/level_01/runs/20260721T075038981227Z__level_01__parameter_sweep__extreme_point_simulated_annealing__seeds3_10be15e3`.
- Rank 1 within this declared grid: initial temperature 0.05, cooling rate 0.95, 200 iterations.
- Rank-1 mean occupied bounding volume: 33,794,376,666.67 mm3; cross-seed standard deviation: 283,388,067.20 mm3.
- Rank-1 objective remained 10992 with two containers and cost 1810 on every seed; three representative source runs were revalidated independently after the sweep.
- Promoted scoped config: `config/level_01/experiments/extreme_point_simulated_annealing_tuned_i20_c5_local.yaml`.
- Tuned-config smoke run: `outputs/level_01/runs/20260721T075200002925Z__level_01__extreme_point_simulated_annealing__i20_c5__seed42`; FEASIBLE and independently VALID.

## Larger heuristic smoke test

- Instance: 50 items, 8 available containers.
- Status: FEASIBLE; independent validation: valid, 0 issues.
- Used containers: C3, C5, C7; algorithm runtime: 0.041 seconds.
- Run: `outputs/level_01/runs/20260721T052238580594Z__level_01__extreme_point_ffd__i50_c8__seed42`.
- Hill Climbing rerun: FEASIBLE/VALID, same three containers and objective, 1.060 seconds; the FFD solution was already a local optimum for configured neighborhoods.
- Hill run: `outputs/level_01/runs/20260721T055515082242Z__level_01__extreme_point_hill_climbing__i50_c8__seed42`.
