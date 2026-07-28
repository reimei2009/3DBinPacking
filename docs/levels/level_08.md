# Level 8 — Delivery order, LIFO, and multiple stops

Status: **CLI-only experimental runtime**. Level 8 remains hidden from
Streamlit. Frozen fixtures remain regression evidence; config-driven Best Fit
and FFD accept declared delivery metadata but are not yet production solvers.

The fixture semantic baseline is recorded in
`docs/reports/manual/level_08_fixture_baseline.md`.

## Activated semantics

Each item may explicitly declare `delivery_priority`, `delivery_stop_id`, and
`delivery_data_source`. A smaller positive `delivery_priority` is delivered
earlier. Multiple items may share one stop/priority, but one priority cannot
refer to multiple stop IDs.

The initial unloadability model is `straight_path_static_lifo_v1`:

- the configured door is `x_min` by default, with the static exit direction
  `-x`;
- a potential blocker is in the same container, closer to the door, and has a
  positive overlap with the moved item's swept cross-section;
- a blocker with later delivery priority is a LIFO violation and contributes
  one direct rehandle to the static lower-bound count;
- earlier/same-stop blockers remain in the audit trail but are not counted as
  rehandles because they can be removed before the target.

The pure engine supports `x_min`, `x_max`, `y_min`, and `y_max` configuration
values. This does not yet model a physical door opening, lifting, rotation,
staging space, or an executable removal sequence.

## Fixture output contract

A fixture writer can persist independent evidence only under
`outputs/level_08/runs/<run_id>/` and include:

- `solution/unloading_accessibility.csv`;
- `solution/rehandle_plan.csv`;
- `validation/unloading_validation.json`.

These artifacts must record door face, clearance, priority convention, blocker
IDs, direct accessibility, LIFO status, and rehandle count.

`level_08_fixture_validation_bundle` is the validation-only CLI algorithm. It
prepares a versioned fixture input, validates the inherited Level 1--7 bundle,
then independently validates static unload/LIFO evidence. It never reads a
previous run output or invokes a solver.

Run the fixture:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_experiment.py `
  --level level_08 --algorithm level_08_fixture_validation_bundle `
  --items-count 2 --containers-count 1 --environment local `
  --non-interactive --preview-limit 0
```

The run must return `VALIDATION_ONLY` and include all inherited evidence plus
`unloading_accessibility.csv`, `rehandle_plan.csv`, and
`unloading_validation.json` under its isolated Level 8 run directory.

The A/B fixture verifies that a delivery-aware Best Fit tie-break, after
container count, cost, and all inherited hard constraints, can avoid a
later-delivery blocker. The baseline deliberately uses ordinary Best Fit and
is expected to be `INVALID_SOLUTION`; the aware variant must be `FEASIBLE` and
`VALID`:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_experiment.py `
  --level level_08 --algorithm extreme_point_best_fit_delivery_aware_fixture `
  --config config\level_08\experiments\delivery_best_fit_aware_fixture.yaml `
  --items-count 2 --containers-count 1 --environment local `
  --non-interactive --preview-limit 0
```

`delivery_multi_stop_multi_container_*_fixture.yaml` extends this evidence to
four items across two payload-forced containers and two stops (`STOP-A`, then
`STOP-B`). It proves that each container receives independent COG and LIFO
evidence. The baseline remains expected-invalid; the aware variant must be
deterministic and `VALID`. This is still a frozen fixture, not arbitrary input
support.

Before enabling delivery-aware FFD, the CLI-only
`extreme_point_ffd_delivery_negative_control_fixture` proves its fixed
container semantics: `C1` can hold both items but creates a LIFO violation;
`C2` can hold the early item, yet canonical FFD retains the first geometrically
feasible container and correctly reports `INVALID_SOLUTION`. This is expected
evidence, not a solver failure to hide with fallback.

`extreme_point_ffd_delivery_aware_fixture` then uses the same two-container
fixture. It preserves `C1` as the first feasible container, but evaluates its
feasible extreme points (including the declared far-door anchor) and selects a
LIFO-valid placement. Thus it is not global Best Fit or a hidden fallback.

For config-driven local experiments, use `extreme_point_best_fit_delivery`
(primary) or `extreme_point_ffd_delivery` (fast comparator). Both require every
selected row to declare priority, stop, and provenance. Missing or ambiguous
delivery metadata fails before solver execution. Level 8 remains CLI-only until
the 20–300 item acceptance protocol passes.

When constructive placement is valid through Level 7 but fails strict LIFO,
the runtime performs bounded local delivery repair on compound roots. It ranks
the largest direct blocker contributors and attempts, in order, in-container
relocation/transfer, leaf swap, and a 4/8/12-root conflict-neighborhood
destroy/reinsert with complete support closures. Each operator has reserved
candidate and time quotas, so relocation cannot consume the swap or
neighborhood budget.
Each accepted intermediate is independently valid through Level 7; only a
final Level 8-valid result is reported as feasible. A monotonic 45-second
deadline (by default) now covers construction and repair together. Construction
checks that deadline between candidates; if it expires, the run returns
`TIME_LIMIT`, writes status evidence only, suppresses the objective, and does
not start repair. Repair receives only the remaining budget, reserves a
separate rescue phase, and may open at most one additional container only after
fixed-container repair. It never rebuilds all selected items.

The delivery-aware construction pass uses reverse loading order: later delivery
priorities are placed first toward the far side, then earlier deliveries are
placed nearer the door. This produces the requested early-stop-near-door final
layout while avoiding the infeasibility caused by trying to occupy door space
with early items before later items have a feasible support-constrained route.
For small instances the runtime can compare this pass with compact construction;
the 300-item profile uses delivery-first directly to preserve its 45-second
pipeline budget.

The final controlled acceptance fixture has three ordered stops (`STOP-A`,
`STOP-B`, `STOP-C`), six items, and two payload-forced containers. The Best
Fit baseline intentionally creates direct later-priority blockers. Delivery-
aware Best Fit and FFD must both remain deterministic, use two containers,
write independent evidence for each container, and finish `VALID`. It does not
enable arbitrary input sizes or change the primary objective.

## Data and provenance

Legacy 3DBPPsi rows do not have delivery metadata. They are preserved as
`unloading_disabled_undeclared`; no priority is inferred from dimensions,
weight, nesting, stackability, or input order.

`data/raw/level_08/unloading_semantic_fixture_items.csv` is a tracked synthetic
semantic fixture. Configured company CSV aliases are normalized through the
shared source adapter. Reproducible scale profiles create untracked synthetic
inputs for 500–5000 items and 50–200 containers; their YAML profile and seed
are the source of truth.

## Inactive

- delivery-aware metaheuristic solvers beyond bounded local repair;
- exact removal-sequence optimization;
- loading order, handling equipment, time, staging space, and door geometry;
- vehicle axle/floor-zone constraints, dynamic transport loads, and vehicle
  certification.
