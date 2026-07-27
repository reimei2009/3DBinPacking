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

The same controlled Best Fit A/B pair also has right-heavy and symmetric profiles. They
are regression acceptance fixtures, not a performance benchmark: right-heavy
must select the left support position, while the symmetric profile keeps the
same deterministic placement and equivalent balance evidence for both scores.

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

The accepted three-profile A/B evidence is recorded in
`docs/reports/manual/level_07_balance_fixture_baseline.md`.

Level 7 also exposes a controlled First-Fit A/B pair:
`extreme_point_ffd_balance_fixture` and
`extreme_point_ffd_balance_baseline_fixture`. Both preserve First Fit's
container decision: they stop at the first feasible container. The aware
variant evaluates every feasible extreme-point/orientation candidate *only in
that container* and ranks it by prospective balance-band violation, total COG
offset, then the canonical FFD order `(z, y, x, orientation)`. The baseline
uses canonical FFD unchanged. The left-heavy fixture therefore has the same
negative-control result as Best Fit: baseline `TOP x=0` is invalid, while the
aware FFD selects `TOP x=200` and validates. Right-heavy selects left; the
symmetric profile retains the canonical FFD tie outcome.

Run the FFD A/B pair on the left-heavy fixture:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_experiment.py `
  --level level_07 `
  --algorithm extreme_point_ffd_balance_baseline_fixture `
  --config config\level_07\experiments\ffd_balance_baseline_fixture.yaml `
  --non-interactive --preview-limit 0

.\.venv\Scripts\python.exe .\scripts\run_experiment.py `
  --level level_07 `
  --algorithm extreme_point_ffd_balance_fixture `
  --config config\level_07\experiments\ffd_balance_aware_fixture.yaml `
  --non-interactive --preview-limit 0
```

The baseline intentionally exits with `INVALID_SOLUTION` (exit code `2`); that
is expected A/B evidence, not a runtime failure.

## Multi-container acceptance fixtures

`balance_two_container_best_fit_fixture.yaml` and
`balance_two_container_ffd_fixture.yaml` force two physical containers. Each
used container has an independent COG record and must pass the final balance
band. They are semantic acceptance fixtures only, not a performance benchmark.

`ffd_first_fit_container_scope_negative_fixture.yaml` is the complementary
negative control. Its first feasible container is geometrically valid but
unbalanced, while a later container would have a better COG. Balance-aware FFD
must remain in the first container and end as `INVALID_SOLUTION`; its metadata
records `balance_container_selection_scope=first_feasible_container_only`.

When using `--interactive`, selecting a Level 7 algorithm now automatically
selects its matching fixture config and prints its frozen inputs. For example,
the balance-aware FFD fixture is always `3 items / 1 container / prefix /
local`; it intentionally does not accept arbitrary counts such as `20/5`.
