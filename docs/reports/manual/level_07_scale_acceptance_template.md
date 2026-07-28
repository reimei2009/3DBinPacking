# Level 7 scale acceptance record

This document is completed manually after running the Level 7 acceptance suite.
Generated outputs remain under `outputs/level_07/runs/` and are not committed.

## Protocol

```powershell
.\.venv\Scripts\python.exe .\scripts\run_benchmark.py `
  --suite config\level_07\benchmarks\primary_best_fit_acceptance_local.yaml

.\.venv\Scripts\python.exe .\scripts\run_benchmark.py `
  --suite config\level_07\benchmarks\ffd_comparator_local.yaml
```

For each completed run, execute:

```powershell
.\.venv\Scripts\python.exe .\scripts\assess_level7_acceptance.py `
  --run-dir outputs\level_07\runs\<run_id> `
  --max-runtime-seconds 45
```

## Required evidence

- Run ID and input fingerprint/checksum.
- Algorithm, seed, item/container counts, runtime and used-container count.
- `VALID` result from the independent Level 7 bundle.
- `center_of_mass.csv` and `balance_validation.json` for every used container.
- `balance_lns_*` metadata: affected containers, destroyed roots, rounds,
  candidates and termination reason.
- Deterministic repeat result for every accepted profile.
- Prefix profiles `20/5`, `100/10`, `300/25` and stable-random `300/25`
  selection seeds `101`, `202`, `303`.
- Explicit `balance_outcome_class`; used containers may exceed the matching
  Level 6 baseline by at most one.

## Promotion gate

Level 7 is ready to close only after every Best Fit primary run is independently
`VALID`, both repeats are deterministic, runtime stays within 45 seconds, no
run exceeds its recorded Level 6 baseline by more than one container, and
Levels 1--6 have no regression. FFD failures are comparator evidence and do not
block the primary gate. Invalid runs must never report an objective.

Create the final baseline table from existing artifacts:

```powershell
.\.venv\Scripts\python.exe .\scripts\build_level7_baseline_report.py `
  --primary-benchmark-dir outputs\level_07\runs\<primary_benchmark_run> `
  --comparator-benchmark-dir outputs\level_07\runs\<ffd_benchmark_run>
```

Level 8 remains paused until this gate is signed off.

This closes an R&D baseline only. The synthetic balance band is not a vehicle
certification standard.
