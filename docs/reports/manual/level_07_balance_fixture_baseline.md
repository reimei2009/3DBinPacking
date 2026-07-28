# Level 7 balance-scoring fixture baseline

## Scope and provenance

- Level: `level_07`, CLI-only; Streamlit remains hidden.
- Constructors: canonical/prospective-COG Extreme Point Best Fit, plus a
  canonical/prospective-COG First Fit pair that preserves first-feasible
  container selection.
- Shared constraints: compound geometry, exact support, base-center support,
  stackability, static load transfer, and final center-of-mass balance.
- Profile: `symmetric_center_band_v1`, target longitudinal COG ratio `0.5`,
  maximum offset `0.15`.
- Every fixture uses prefix selection, 3 items, 1 container, local environment,
  fixed XYZ orientation, and seed 42.

These are deterministic acceptance fixtures, not a performance benchmark or a
claim of practical transport certification.

## A/B results

| Profile | Baseline Best Fit | COG-aware Best Fit | Decision evidence |
| --- | --- | --- | --- |
| Left-heavy | `TOP x=0`; `INVALID_SOLUTION`; longitudinal offset `0.178571` | `TOP x=200`; `FEASIBLE` + `VALID`; offset `0.035714` | The score moves the top item opposite the heavy base and crosses the final balance band. |
| Right-heavy | `TOP x=0`; `FEASIBLE` + `VALID`; offset `0.036250` | `TOP x=0`; `FEASIBLE` + `VALID`; offset `0.036250` | The score does not reverse an already balanced canonical Best Fit decision. |
| Symmetric | `TOP x=0`; `FEASIBLE` + `VALID`; offset `0.083750` | `TOP x=0`; `FEASIBLE` + `VALID`; offset `0.083750` | The score preserves the deterministic tie outcome and adds no directional bias. |

All completed solutions use one container with the same synthetic cost and the
same geometry/support/load-transfer constraints. The left-heavy baseline is
intentionally invalid: it is the negative control proving that final validation
is still authoritative.

## Decision

- Keep prospective COG as a **soft Best Fit tie-break**.
- Keep Level 7 balance as a **hard final independent validation**.
- FFD was ported only through a separate intra-container selection policy;
  First Fit container semantics remain intact. Do not generalize it beyond
  these fixtures until a broader acceptance benchmark is approved.

## First Fit acceptance extension

The controlled FFD pair is now implemented with a strictly narrower COG hook:
it never changes the first feasible container. Within that one container it
ranks feasible candidates by balance-band violation, COG offset, then canonical
FFD `(z, y, x, orientation)` order. It has the same acceptance outcomes as the
Best Fit table above: left-heavy baseline `TOP x=0` is invalid whereas aware
FFD selects `TOP x=200` and is valid; right-heavy selects left; symmetric keeps
the deterministic canonical tie. This remains fixture evidence, not a
production-scale FFD benchmark.

## Multi-container scope evidence

The two-container positive fixture forces one full-floor item into each of C1
and C2. Both Best Fit and FFD produce two independent balanced COG records and
pass the full inherited Level 6 plus Level 7 validator.

The FFD container-scope negative control uses a cheaper, wider C1 and a later
perfect-fit C2. The single item is geometrically feasible in C1 but unbalanced;
FFD deliberately keeps C1, emits `INVALID_SOLUTION`, and records
`first_feasible_container_only`. This proves the COG policy is not an implicit
global container-selection heuristic.
