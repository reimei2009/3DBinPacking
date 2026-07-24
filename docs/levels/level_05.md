# Level 5 — Load-bearing and recursive load transfer

Status: **solver portfolio validated with Best Fit, FFD, Hill Climbing and SA**.

The Level 5 contract is defined in
`docs/specs/level5/level5_data_contract.md` and
`config/level_05/load_bearing_rules.yaml`. It inherits Level 4 and is
registered as an executable, output-isolated level.

The objective remains minimum used-container count followed by minimum
container cost. Load-bearing will be a hard feasibility constraint rather
than an objective term.

The engine distributes accumulated static vertical load by exact contact-area
fractions and the validator recomputes capacity, conservation, overload, and
fragility from canonical placements without solver state.

Extreme Point Best Fit rejects a candidate whenever recomputing the projected
contact graph would overload an item or place load above a fragile item. The
independent validator recomputes the final graph and writes:

- `solution/load_bearing.csv`;
- `solution/load_transfer.csv`;
- `validation/load_bearing_validation.json`.

Best Fit remains the practical default. FFD uses the same load-bearing policy
as a deterministic constructive comparator. Hill Climbing uses Best Fit for
both initialization and repair, so every destroy-and-repair candidate is
filtered through the same policy. Other Level 4 algorithms are intentionally
inactive at Level 5 in this checkpoint. Pressure, moments, deformation,
dynamic load and full mechanical stability remain out of scope.

Simulated Annealing uses the inherited seeded Level 4 quality parameters and
the same Best-Fit initialization/repair. It is a quality comparator only, not
a practical default.

Before promoting any Level 5 SA setting, run both frozen sensitivity profiles:

```powershell
python scripts\run_parameter_sweep.py --config config\level_05\sweeps\sa_prefix_i20_c5_local.yaml
python scripts\run_parameter_sweep.py --config config\level_05\sweeps\sa_stable_random_101_i20_c5_local.yaml
```

Each sweep has 8 parameter sets × 3 seeds. Compare success rate, worst/mean
container count, cost, compactness and runtime; do not select a quality
profile from one input profile alone.

## Solver portfolio

| Profile | Solver | When to use |
| --- | --- | --- |
| Fast | Extreme Point Best Fit | Interactive/local operation. |
| Balanced | Hill Climbing with Best Fit repair | Moderate local-search budget. |
| Quality | SA p006 (`200`, `0.05`, `0.99`) | Difficult profiles where fewer containers justify a longer runtime. |

The Level 5 sweeps select p006 because it matched the best prefix primary
objective and was the only set to keep two containers on
`stable_random_101_i20_c5` for all seeds. Validate the portfolio manually:

```powershell
python scripts\run_benchmark.py --suite config\level_05\benchmarks\portfolio_local.yaml
```

The accepted baseline is recorded in
`docs/reports/manual/level_05_portfolio_baseline_20260724.md`. It confirms
that all 18 portfolio source runs were independently valid and that inputs
were identical within each scenario.
