# Level 7 data contract — container center of mass and balance

Status: **data contract plus pure engine/fixture validator; no runtime is
registered**.

Level 7 will inherit all Level 6 constraints and use the existing item
`weight_kg`, placement dimensions, and coordinates to compute a per-container
center of mass. This checkpoint does not alter any prior level, solver,
validator, objective, CLI option, UI option, or output directory.

## Future center-of-mass model

For each used container \(k\), with item geometric centers
\((x_i + l_i/2, y_i + w_i/2, z_i + h_i/2)\):

\[
X_k^{cg}=\frac{\sum_{i\in k} w_i(x_i+l_i/2)}{\sum_{i\in k}w_i},\qquad
Y_k^{cg}=\frac{\sum_{i\in k} w_i(y_i+w_i/2)}{\sum_{i\in k}w_i}.
\]

The initial balance profile constrains normalized horizontal offsets:

\[
\left|X_k^{cg}/L_k-t^x_k\right|\le\tau^x_k,\qquad
\left|Y_k^{cg}/W_k-t^y_k\right|\le\tau^y_k.
\]

`x` is longitudinal and `y` is lateral. The vertical center of mass is
reported by the pure engine but is not a feasibility constraint.

## Canonical profile fields

| Field | Meaning |
| --- | --- |
| `target_longitudinal_ratio` | Target normalized longitudinal COG, in `[0, 1]`. |
| `target_lateral_ratio` | Target normalized lateral COG, in `[0, 1]`. |
| `max_longitudinal_offset_ratio` | Allowed normalized longitudinal offset, in `[0, 0.5]`. |
| `max_lateral_offset_ratio` | Allowed normalized lateral offset, in `[0, 0.5]`. |
| `balance_profile_source` | Provenance of the target and tolerance values. |

`config/level_07/balance_rules.yaml` defines the synthetic research profile
`symmetric_center_band_v1`, with target `(0.5, 0.5)` and both tolerances
`0.15`. It supports explicit physical-container overrides. The values are not
vehicle certification data and must not be inferred from `max_weight_kg`, item
weight, stackability, or load-bearing capacity.

## Future output contract

When Level 7 runtime is approved, it will write only under
`outputs/level_07/runs/<run_id>/`:

- `solution/center_of_mass.csv`;
- `validation/balance_validation.json`.

## Current implementation boundary

`center_of_mass.py` computes mass-weighted COG from canonical placements and
the versioned balance profile. `level_07_validation.py` independently checks
source-item/placement identity and weight consistency before recomputing the
balance evidence. `level_07_fixture_bundle.py` composes that evidence with the
Level 6 compound-root nesting/support/stackability/load-transfer bundle on one
synthetic fixture. `level_07_fixture_output.py` can persist that evidence only
under `outputs/level_07/runs/<run_id>` and refuses overwrite. None is connected
to a runtime, CLI, UI, or solver.

`config/level_07/runtime_candidate.yaml` freezes the placeholder output schema,
acceptance fixture, and manual promotion gate. It deliberately does not add
Level 7 to the registry.

## Explicitly inactive in this checkpoint

Floor-zone load limits, door clearance, axle limits, dynamic transport loads,
rollover stability, moments, and suspension modelling are not yet defined.
They require separate allocation and vehicle semantics and therefore are not
silently represented by the COG profile.
