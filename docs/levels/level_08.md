# Level 8 — Delivery order, LIFO, and multiple stops

Status: **fixture-only independent validation evidence**. Level 8 is not in
the runtime registry, has no solver, does not change the optimization
objective, and has no CLI/UI experiment entrypoint.

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

`level_08_fixture_validation_bundle` is an internal writer identifier, not a
registered algorithm. It never invokes a solver and is used only by tests until
the runtime-candidate gate is explicitly approved.

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

- delivery-aware constructive or metaheuristic solvers;
- exact removal-sequence optimization;
- loading order, handling equipment, time, staging space, and door geometry;
- vehicle axle/floor-zone constraints, dynamic transport loads, and vehicle
  certification.
