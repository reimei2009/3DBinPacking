# Level 7 balance-scoring fixture baseline

## Scope and provenance

- Level: `level_07`, CLI-only; Streamlit remains hidden.
- Constructors: canonical Extreme Point Best Fit baseline and prospective-COG
  Best Fit.
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
- Do not port FFD yet. The next candidate should be considered only after a
  separate design decision for FFD candidate ranking, because classic First Fit
  does not evaluate all feasible placements in the same way as Best Fit.
