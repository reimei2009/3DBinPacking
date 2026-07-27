# Level 7 — Center of mass and balance (CLI acceptance fixture)

Level 7 is registered only as a controlled CLI acceptance fixture. Its sole
algorithm, `level_07_fixture_validation_bundle`, loads a frozen four-item,
one-container, prefix-selected local fixture and independently validates the
inherited Level 6 compound geometry, nesting, support, stackability and static
load-transfer evidence together with Level 7 center-of-mass balance.

It returns `VALIDATION_ONLY`, not `FEASIBLE`, `OPTIMAL`, or an objective value.
No packing solver, arbitrary item count, runtime selection policy, orientation
choice, or optimization objective is exposed. Streamlit intentionally hides
this level.

Run it from the repository root:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_experiment.py `
  --level level_07 `
  --config config\level_07\experimental.yaml `
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
