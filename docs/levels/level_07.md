# Level 7 — Center of mass and balance (CLI acceptance fixture)

Level 7 is registered only for controlled CLI experiments. The acceptance
algorithm `level_07_fixture_validation_bundle` loads a frozen four-item,
one-container, prefix-selected local fixture and independently validates the
inherited Level 6 compound geometry, nesting, support, stackability and static
load-transfer evidence together with Level 7 center-of-mass balance.

It returns `VALIDATION_ONLY`, not `FEASIBLE`, `OPTIMAL`, or an objective value.
The additional `extreme_point_best_fit_balance_fixture` is a separate frozen
three-item discriminator fixture: it uses prospective COG only as a Best Fit
tie-break, then requires independent final balance validation. Neither runtime
accepts arbitrary input or is visible in Streamlit.
`extreme_point_best_fit_balance_baseline_fixture` runs the same input with the
canonical Best Fit score only; it is an A/B comparator and is expected to fail
final balance validation on this deliberately asymmetric fixture.

Run it from the repository root:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_experiment.py `
  --level level_07 `
  --config config\level_07\experimental.yaml `
  --non-interactive --preview-limit 0
```

Run the balance-aware Best Fit fixture:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_experiment.py `
  --level level_07 `
  --algorithm extreme_point_best_fit_balance_fixture `
  --config config\level_07\experiments\balance_aware_best_fit_fixture.yaml `
  --non-interactive --preview-limit 0
```

Run its canonical Best Fit A/B comparator (an `INVALID_SOLUTION` exit is the
expected acceptance result):

```powershell
.\.venv\Scripts\python.exe .\scripts\run_experiment.py `
  --level level_07 `
  --algorithm extreme_point_best_fit_balance_baseline_fixture `
  --config config\level_07\experiments\balance_baseline_best_fit_fixture.yaml `
  --non-interactive --preview-limit 0
```

Validate a completed run independently:

```powershell
.\.venv\Scripts\python.exe -m container_packing.cli validate `
  --level level_07 --run-dir outputs\level_07\runs\<run_id>
```

Each run is isolated under `outputs/level_07/runs/<run_id>/` and includes the
canonical placements, nesting relations, compound/support/stack/load artifacts,
`solution/center_of_mass.csv`, and `validation/balance_validation.json`.

The active COG model and its synthetic balance band are documented in
`docs/specs/level7/level7_balance_data_contract.md`. It does not represent
vehicle certification, dynamic stability, floor-zone loads, axle loads, door
clearance, or a practical balance-aware packing solver.
