# Level 8 — Delivery order, LIFO, and multiple stops

Status: **CLI-only experimental fixtures**. Level 8 remains hidden from
Streamlit. It has a validation-only fixture plus a small Best Fit A/B fixture;
neither is an arbitrary-instance or production delivery solver.

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

- arbitrary-instance delivery-aware constructive or metaheuristic solvers;
- exact removal-sequence optimization;
- loading order, handling equipment, time, staging space, and door geometry;
- vehicle axle/floor-zone constraints, dynamic transport loads, and vehicle
  certification.
