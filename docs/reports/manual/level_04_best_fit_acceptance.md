# Level 4 Best Fit acceptance procedure

This procedure freezes the practical Level 4 baseline before any additional
Level 4 heuristic is enabled. It evaluates stackability-aware Extreme Point
Best Fit under one shared input per scenario.

## Run

From the repository root with the virtual environment active:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_benchmark.py `
  --suite config\level_04\benchmarks\best_fit_baseline_local.yaml
```

The suite includes a tiny smoke case and larger practical/scale cases. It is
intentionally manual because it creates 18 isolated experiment runs (six
scenarios times three deterministic repeats). The command prints only the
aggregate table and the benchmark directory.

## Acceptance checks

Open `benchmark/results.csv`, `benchmark/summary.csv`, and `benchmark/ranking.csv`
in the printed benchmark directory. For a representative source run, inspect
`validation/support_validation.json`, `validation/stack_validation.json`,
`solution/support.csv`, and `solution/stacks.csv`.

| Check | Expected result |
| --- | --- |
| Contract | Every row has `level=level_04`, `orientation_profile=horizontal_rotatable`, and feasibility policy `horizontal_orientation_geometry_payload_exact_support_stackability`. |
| Validity | Every completed row has `success=True`, `validation_valid=True`, and exact support ratio at least the configured support threshold. |
| Stackability | `stack_validation.json` is valid; every non-floor item has a direct parent with the same `stackability_code`, and every parent chain observes the configured cap. |
| Fairness | All repeats of one `scenario_id` share one `input_fingerprint` and one selected-item checksum. |
| Determinism | Repeats of one scenario have one `placement_signature` and one objective value. |
| Quality | Compare used containers first, then cost, then compactness. Runtime is reported separately and must not be judged without these quality values. |

Do not rank a row with `success=False` or `validation_valid=False`. The
absence of a feasible heuristic result means only that Best Fit did not
construct a valid packing for that input; it is not a proof that the packing
problem is infeasible.

## Record

Record the generated benchmark directory and summarize the result by scenario
in a generated report under `outputs/level_04/`. Do not commit generated runs
or copy their CSV files into source documentation.

## Constructive comparison

After the Best Fit baseline passes, compare all active constructive solvers:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_benchmark.py `
  --suite config\level_04\benchmarks\core_constructive_local.yaml
```

Use only rows from that one benchmark directory for the comparison. Best Fit
is the practical default; FFD and Maximal Empty Spaces remain deterministic
comparators.

## Best Fit versus Hill Climbing

Run the local-search comparison manually; it includes repeated `i20/c5` cases:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_benchmark.py `
  --suite config\level_04\benchmarks\local_search_local.yaml
```

Require every completed row to be `VALID`. Hill Climbing may be slower, so
compare container count, cost, and compactness before treating it as an
improvement over Best Fit.

## Metaheuristic comparison

Run the seeded Simulated Annealing comparison manually:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_benchmark.py `
  --suite config\level_04\benchmarks\metaheuristic_local.yaml
```

Compare only rows from this benchmark directory. For the fixed seed, repeats
must have one placement signature and objective; `VALID` remains mandatory.

## SA sensitivity by item profile

Run the two SA sweeps manually. Each one has 24 source runs and tests three
search seeds, so it is intentionally not part of automated tests.

```powershell
.\.venv\Scripts\python.exe .\scripts\run_parameter_sweep.py `
  --config config\level_04\sweeps\sa_prefix_i20_c5_local.yaml
```

```powershell
.\.venv\Scripts\python.exe .\scripts\run_parameter_sweep.py `
  --config config\level_04\sweeps\sa_stable_random_101_i20_c5_local.yaml
```

Inspect `sweep/ranking.csv`, `sweep/best_parameters.json`, and per-seed
quality variation before selecting a future quality profile. Do not compare
parameter sets from different sweep directories as one ranking.

## Solver portfolio acceptance

The selected SA quality profile is p006: 200 iterations, temperature 0.05,
and cooling rate 0.99. Run the portfolio comparison manually:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_benchmark.py `
  --suite config\level_04\benchmarks\portfolio_local.yaml
```

This creates 18 source runs. Compare only rows with the same `scenario_id`
and input fingerprint. Best Fit remains the default; quality gains from SA
must be weighed against runtime.
