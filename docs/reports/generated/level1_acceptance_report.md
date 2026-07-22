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
- Pytest: 89 passed, 0 failed.
- The reference notebook passes `nbformat.validate` and a clean in-memory execution reports `OPTIMAL` with `validation_valid: true`.

## Solver and independent validation

- Status: OPTIMAL (HiGHS Status 7)
- Objective: 10992.0
- Selected containers: C2, C4
- Container count: 2
- Synthetic cost: 1810.0
- Placed items: 20/20
- Independent validation: valid, 0 issues

The solution has no boundary, overlap, payload, identity, dimension, or weight violations. Physical support/stability is intentionally not evaluated at Level 1.

## Config-driven research corpus acceptance evidence

- Corpus: `config/level_01/benchmarks/research_corpus.yaml`; five named cases covering small/easy, payload-tight, proven infeasible, medium, and large local-CPU profiles.
- Aggregate run: `outputs/level_01/runs/20260722T035103835314Z__level_01__benchmark_corpus__level1_research_v1__seed42`.
- Executions: 26/26 matched the declared expected outcome; every feasible source run passed the independent Level 1 validator.
- `small_easy_i5_c2` and `small_tight_i10_c2` have MILP `proven_optimal` references. Every tested heuristic matched the exact count/cost objective on both cases.
- `small_infeasible_i10_c1` has a MILP `proven_infeasible` reference because the first ten items weigh 2,845.128 kg while the only configured C1 container permits 1,500 kg. Heuristic failures remain labelled `INFEASIBLE_HEURISTIC` and are not treated as proofs.
- `medium_mixed_i50_c8` and `large_scalability_i100_c15` use `best_known` references, not optimality claims. Simulated Annealing supplied the medium reference; FFD and Extreme-Point Best Fit supplied the tied large reference.
- Representative 5-item MILP, 50-item Simulated Annealing, and 100-item FFD source runs were revalidated separately with zero issues.
- Streamlit AppTest opened the persisted corpus on demand and rendered two comparison charts without exceptions: objective gap to reference and log-scale algorithm runtime.
- The corpus writes case catalog, raw results, aggregate summary, per-case ranking, reference table, resolved config, manifest, logs, and source-run links under its isolated Level 1 run directory.

## Maximal Empty Spaces Best Fit acceptance evidence

- Algorithm: `maximal_space_best_fit`, deterministic and CPU-only.
- Standalone 20-item/5-container run: `outputs/level_01/runs/20260721T110527949807Z__level_01__maximal_space_best_fit__i20_c5__seed42`.
- Status: FEASIBLE; independent validation: valid, 0 issues; selected containers: C2+C4; objective: 10992.
- Exact comparison matrix: 6 algorithms × 2 item counts × 2 container counts = 24 successful, independently validated cases.
- Aggregate run: `outputs/level_01/runs/20260721T110543282257Z__level_01__benchmark__seed42`.
- On 20 items/5 containers, EMS matched the MILP-optimal count/cost objective in 0.001230 seconds; MILP took 4.521602 seconds. The status remains FEASIBLE because EMS does not prove optimality.
- A deterministic differentiating fixture is covered by regression test: EMS packs five fixed-orientation items into one 10×10×10 container while the current Extreme-Point Best Fit candidate set returns `INFEASIBLE_HEURISTIC`.
- Larger constructive matrix: 3 algorithms × item counts 50/100 × container counts 8/15 = 12 valid cases; aggregate run `outputs/level_01/runs/20260721T110613445743Z__level_01__benchmark__seed42`.
- EMS runtime ranged from 0.003475 to 0.108548 seconds in that matrix. The 100-item/15-container case used four containers while both Extreme-Point baselines used three, so EMS is retained as a complementary geometric baseline rather than described as uniformly superior.
- The EMS 100-item/15-container source run was revalidated separately: valid, 0 issues. Its diagnostics recorded 4,107 empty spaces evaluated, 1,375 generated, 809 pruned, and at most 30 active spaces.

## Extreme-Point Best Fit acceptance evidence

- Algorithm: `extreme_point_best_fit`, deterministic and CPU-only.
- Standalone 20-item/5-container run: `outputs/level_01/runs/20260721T103352569442Z__level_01__extreme_point_best_fit__i20_c5__seed42`.
- Status: FEASIBLE; independent validation: valid, 0 issues; selected containers: C2+C4; objective: 10992.
- Exact comparison matrix: 5 algorithms × 2 item counts × 2 container counts = 20 successful, independently validated cases.
- Aggregate run: `outputs/level_01/runs/20260721T103401385475Z__level_01__benchmark__seed42`.
- On 20 items/5 containers, Best Fit matched the MILP-optimal count/cost objective and reduced occupied bounding volume from FFD's 35,517,519,000 to 31,209,130,000 mm3 (12.13% lower); runtime was 0.001800 versus 0.000831 seconds.
- On 50 items/8 containers, Best Fit and FFD both used three containers with objective 31403 and identical geometry; Best Fit took 0.093771 versus 0.040758 seconds. Simulated Annealing found a better two-container solution on this instance, so Best Fit is retained as a constructive baseline rather than described as uniformly superior.
- Large-heuristic aggregate run: `outputs/level_01/runs/20260721T103436191047Z__level_01__benchmark__seed42`; all four heuristic solutions were independently valid.
- The refactored FFD 50-item placements CSV has the same SHA-256 as the pre-refactor accepted run, confirming unchanged canonical geometry.

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

## Reusable web and 3D visualization evidence

- Streamlit AppTest changed the interactive instance to 10 items and 3 containers, executed the shared Extreme-Point FFD pipeline, and rendered one Plotly chart.
- Status: FEASIBLE; independent validation: valid, 0 issues; used containers: 1.
- Scene contract: schema 1.0, lower-left-back coordinates in millimeters, stable item IDs, container utilization, and an explicit Level 1 physical-stability warning.
- Derived views: `visualization/combined_scene.html` and one `visualization/container_<id>.html` per used container.
- The core package, application boundary, and scene builder have no dependency on Streamlit; the UI can be replaced without rewriting optimization or validation logic.
- Vietnamese is the default UI language with an English switch. Streamlit AppTest rendered 15 LaTeX blocks covering notation, constants, four variable groups, the objective, and seven constraint families; every expression retains a canonical code mapping.
- The default 3D view opens one used container with solid items at opacity 0.92. Streamlit AppTest exercised item selection details and item hiding; renderer tests independently verified the Solid/Balanced/X-Ray opacity values, opacity 1.0 for the selected item, 0.20 for dimmed peers, and omission of hidden meshes.
