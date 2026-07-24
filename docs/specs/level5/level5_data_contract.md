# Level 5 data contract — load-bearing

## Status and scope

The data semantics, pure recursive load-transfer engine, independent
load-bearing validator, and isolated Level 5 runtime are implemented. Level 5
is registered in CLI and UI with Extreme Point Best Fit as the practical
default, FFD as a deterministic constructive comparator, and Hill Climbing as
a Best-Fit-initialized local-search comparator. Simulated Annealing is a
seeded quality comparator using the same policy. Levels 1–4 remain unchanged.

Level 5 will inherit Level 4 geometry, horizontal orientation, exact base
support, center support, and stackability. It adds static vertical load
capacity and recursive load transfer. It does not claim full physical
stability.

## Canonical attributes

| Field | Meaning | Validation |
| --- | --- | --- |
| `max_supported_weight_kg` | Maximum load above an item, excluding its own weight | positive for non-fragile items; zero for fragile items |
| `is_fragile` | Item may not carry load from another item | strict boolean |
| `load_capacity_source` | Provenance of strength/fragility values | non-empty string |

The source 3DBPPsi CSV does not contain these fields. The research profile
`synthetic_weight_factor_v1` uses:

```text
max_supported_weight_kg = 4 × weight_kg
```

This is a reproducible experimental assumption, not measured material data.
It must not be described as a real safe working load. `stackability_code` and
`max_stackability` are never used to infer strength.

## Load graph

The load graph is separate from Level 4's unique declared stack-parent
relation `p[j,i,k]`. For every geometric supporter `j` below item `i`:

```text
lambda[j,i] = A[j,i] / sum(A[s,i] for s in S[i])
T[i] = w[i] + sum(lambda[i,h] * T[h] for h directly supported by i)
L[i] = T[i] - w[i]
L[i] <= M[i]
```

`A[j,i]` is exact contact area, `lambda[j,i]` the transfer fraction, `T[i]`
the load transmitted downward including own weight, `L[i]` load above, and
`M[i]` maximum supported load.

## Runtime outputs

- `solution/load_bearing.csv`: per-item capacity, load, utilization, margin,
  fragility, and provenance.
- `solution/load_transfer.csv`: supporter/child edge, contact area, fraction,
  and transferred load.
- `validation/load_bearing_validation.json`: independent recomputation and
  violations.

These files are generated under
`outputs/level_05/runs/<run_id>/`; no Level 5 artifact is written into an
earlier level's output directory.

## Inactive physics

Contact pressure, bending moment, deformation, dynamic load, vibration,
area-specific floor loading, and full mechanical stability remain inactive.
