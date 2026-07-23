# Level 3 — Horizontal orientation (planned)

Status: **implemented for Extreme Point FFD and registered for local execution**.

Level 3 will inherit all Level 2 geometry, payload, floor-contact, exact
base-support-ratio, and base-center-support rules. It adds one decision per
item: whether its horizontal length and width are kept or swapped. Height is
never rotated into a horizontal axis.

For item `i`, the allowed set is `O_i` and the binary selection is `r_io`.
Exactly one orientation is selected:

```text
sum(o in O_i) r_io = 1
```

The two canonical codes are:

| Code | Effective dimensions `(length, width, height)` |
| --- | --- |
| `XYZ` | `(l_i, w_i, h_i)` |
| `YXZ` | `(w_i, l_i, h_i)` |

This is deliberately a horizontal-only rotation model. It preserves the
vertical axis and does not add the four rotations that would place `h_i` on a
horizontal axis.

## Active

- assignment of exactly one allowed orientation;
- orientation-dependent boundary and non-overlap dimensions;
- orientation-dependent support base for Level 2 support checks;
- orientation recorded in canonical placement, scene, report, and validator;
- fixed-orientation Level 1 and Level 2 behavior preserved unchanged.

## Data policy

The raw field `forced_orientation` is preserved but has no verified mapping in
this repository. The current source has `n` for 468 items and `w` for 33
items. Level 3 must not silently interpret those labels.

Until source semantics are independently verified, experiments use an explicit
synthetic orientation profile declared in YAML:

- `fixed`: `O_i = {XYZ}` for every item;
- `horizontal_rotatable`: `O_i = {XYZ, YXZ}` after removing duplicate
  dimensions when `length_mm == width_mm`.

Every synthetic profile must carry `data_status: synthetic_orientation_profile`,
its profile ID, and its configuration in the run manifest. A future verified
mapping from `forced_orientation` must be versioned and documented as a data
transformation; it must not overwrite raw data.

## Out of scope

- rotation that changes the vertical axis;
- stackability, load-bearing, nesting, fragility, balance, or load order;
- a claim of full physical stability.

## Acceptance gate

Level 3 is accepted only after its independent validator recomputes effective
dimensions from the selected orientation, all Level 1–2 regression tests pass,
and FFD produces deterministic valid solutions on the frozen Level 3 fixtures.

## Current solver scope

`extreme_point_ffd` is the only Level 3 solver currently registered. It is the
practical default and evaluates `XYZ` then `YXZ` candidates at each extreme
point using the same exact-support feasibility policy as Level 2. It reports
`INFEASIBLE_HEURISTIC` as a search failure, never a proof of mathematical
infeasibility.

MILP orientation reference, Best Fit, Hill Climbing, Simulated Annealing and
Maximal Empty Spaces are intentionally not yet registered for Level 3.
