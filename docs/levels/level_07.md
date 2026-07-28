# Level 7 — Center of mass and balance

Level 7 is an experimental, compound-aware packing runtime. It inherits Level
6 geometry, nesting, support, stackability, and static load-transfer validation,
then independently validates the mass-weighted center of mass of every used
container.

The web UI exposes two dynamic algorithms:

- `extreme_point_best_fit_balance` — the practical primary solver.
- `extreme_point_ffd_balance` — the fast comparator; profile failure never
  triggers a hidden fallback.

Both accept the normal UI/CLI controls: item count, container count, seed, and
item-selection strategy. They are experimental rather than production solvers.
The primary objective remains inherited from Level 6 (fewest containers, then
cost). Balance is a soft construction tie-break and a hard final independent
validation: an intermediate placement is not rejected just because its partial
COG is outside the target band.

For dynamic runs, Level 7 first constructs a compact Level 6-style solution.
It then uses a bounded local COG repair engine over compound roots. Container
mass and moments are cached, so a relocation or swap is scored without rebuilding
the complete packing. A supporter is never moved alone: its transitive support
closure is moved as one partial-repack candidate. Every local candidate must pass
the Level 6 feasibility policy and every accepted final solution is recomputed by
the independent Level 7 validator.

The default total pipeline budget is 45 seconds including compact construction:
up to 10 seconds of directional local moves, adaptive Large Neighborhood Search
using closure neighborhoods of 4, 8, then 12 roots, and at most 5 seconds with
one additional container. The effective repair budget is reduced by time already
spent constructing the baseline.
The engine checks its cooperative deadline between candidates; one validator
call may exceed it slightly. LNS removes at most eight compound support closures
and re-packs only that neighborhood; it does not perform full-solution rebuilds.
Neighborhood selection is directional: it prioritizes the roots contributing
the greatest mass moment on the overloaded side of the currently violated COG
axis. A supporter and its dependants remain one indivisible repair group.
Local repair, LNS and rescue pass forward the best Level 1--6-valid
intermediate state even when it is not yet balanced. This is search state, not
a solution: only a final Level 7-valid placement may return `FEASIBLE` and an
objective.

If the budget expires without a valid repair, the original compact candidate is
preserved as diagnostic evidence and the run is `INVALID_SOLUTION`. Such a run
has no comparable objective; its candidate objective is metadata only.

The outcome class is explicit: `VALID_FIXED_CONTAINER`,
`VALID_WITH_ONE_EXTRA_CONTAINER`, or
`NO_VALID_BALANCED_SOLUTION_WITHIN_BUDGET`. When a rescue container is used,
the pipeline attempts a bounded consolidation pass before retaining it.

Two operational configs are available: `experiments/strict_local.yaml` never
opens an extra container; `experiments/allow_one_extra_container_local.yaml`
permits one only after local and LNS repair fail. Both return the explicit
metadata failure reason `NO_VALID_BALANCED_SOLUTION_WITHIN_BUDGET` when no valid
balanced result is found.

The manual acceptance protocol separates the primary and comparator:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_benchmark.py `
  --suite config\level_07\benchmarks\primary_best_fit_acceptance_local.yaml

.\.venv\Scripts\python.exe .\scripts\run_benchmark.py `
  --suite config\level_07\benchmarks\ffd_comparator_local.yaml
```

Build the versioned report from those outputs without rerunning solvers:

```powershell
.\.venv\Scripts\python.exe .\scripts\build_level7_baseline_report.py `
  --primary-benchmark-dir outputs\level_07\runs\<primary_benchmark_run> `
  --comparator-benchmark-dir outputs\level_07\runs\<ffd_benchmark_run>
```

Run Best Fit:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_experiment.py `
  --level level_07 --algorithm extreme_point_best_fit_balance `
  --items-count 20 --containers-count 5 --environment local --non-interactive
```

Run the faster First Fit variant:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_experiment.py `
  --level level_07 --algorithm extreme_point_ffd_balance `
  --items-count 20 --containers-count 5 --environment local --non-interactive
```

Each run is isolated in `outputs/level_07/runs/<run_id>/` and includes
`solution/center_of_mass.csv`, `validation/balance_validation.json`, and all
inherited nesting, support, stackability, and load-transfer artifacts. A run is
successful only when the final independent validator returns `VALID`.

## Acceptance fixtures

The frozen CLI-only fixture algorithms remain available for regression and A/B
evidence, but are intentionally hidden from Streamlit:

- `level_07_fixture_validation_bundle`
- `extreme_point_best_fit_balance_fixture` and its baseline
- `extreme_point_ffd_balance_fixture` and its baseline

They use fixed semantic inputs; a baseline can intentionally finish as
`INVALID_SOLUTION` to prove that COG guidance, rather than geometry alone,
causes the balanced placement.

## Limits

The synthetic center-band profile is research provenance, not vehicle
certification. Level 7 does not model axle loads, floor-zone loads, door
clearance, moments, dynamic transport load, rollover, or suspension.

The current code is **ready for manual scale acceptance**, not closed as a
production level. See `docs/reports/manual/level_07_scale_acceptance_template.md`.

## Diagnosing an invalid scale benchmark

Do not re-run a benchmark just to inspect a failed balance candidate. Generate
a report from its isolated source-run artifacts instead:

```powershell
.\.venv\Scripts\python.exe .\scripts\analyze_level7_balance_failures.py `
  --benchmark-dir outputs\level_07\runs\<benchmark_run_id>
```

The report identifies the dominant COG axis/container, excess over the band,
required mass-shift direction, contributor roots and local-repair/LNS stop
reason. It classifies the next operator as leaf relocation, support-closure
partial repack, or controlled extra-container search. Classification is search
evidence, not a proof that a valid repair exists. It treats all costs and
container counts from `INVALID_SOLUTION` runs as diagnostic only.
