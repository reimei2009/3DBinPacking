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

`extreme_point_ffd` is the practical default. `extreme_point_best_fit` is an
alternative deterministic constructive method that scores every feasible
extreme-point/orientation candidate. `extreme_point_hill_climbing` starts from
orientation-aware FFD and uses the same provider during every destroy/repack
neighborhood. `extreme_point_simulated_annealing` uses the same orientation-
aware neighborhood with seeded Metropolis acceptance. `maximal_space_best_fit`
evaluates both horizontal orientations at each maximal-empty-space origin. All
five use the same
exact-support feasibility policy as Level 2 and report
`INFEASIBLE_HEURISTIC` as a search failure, never a proof of mathematical
infeasibility.

`milp_big_m` is also available as an exact reference for at most five items.
It uses sparse Big-M constraints with `XYZ`/`YXZ` binary variables and the
same floor/support grid as Level 2; decoded placements are still validated by
the independent exact-union support validator. It is deliberately rejected
above five items, so it cannot accidentally replace FFD in practical runs.

Run the reference only on its small config:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_experiment.py `
  --level level_03 `
  --algorithm milp_big_m `
  --config config\level_03\experiments\milp_big_m_reference.yaml `
  --non-interactive --preview-limit 0
```

## FFD baseline protocol

The reproducible promotion suite is
`config/level_03/benchmarks/ffd_baseline_local.yaml`. It records the synthetic
orientation profile, selected orientation codes, placement signature, objective,
support validation, and runtime. The `i3/c2` scenario is safe for automated
tests. Run the `i20+` scenarios manually:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_benchmark.py `
  --suite config\level_03\benchmarks\ffd_baseline_local.yaml
```

Inspect `benchmark/results.csv` for repeated `placement_signature`, objective,
`orientation_profile`, and `minimum_exact_support_ratio`; inspect
`benchmark/summary.csv` for timing aggregates. This suite does not compare
against Level 2 directly because benchmark fingerprints intentionally include
the active level contract. The frozen unit fixture in
`tests/test_extreme_point_ffd.py` is the controlled proof that `YXZ` solves a
case where Level 1/2 fixed orientation cannot fit the item.

For the five-method Level 3 comparison, use
`config/level_03/benchmarks/core_heuristics_local.yaml` and follow
`docs/reports/manual/level_03_heuristic_acceptance.md`. It deliberately keeps
the large scale case constructive-only, because local search and SA are not
the practical default at that size.
