# ADR-0007: Add benchmark seed sweeps

Status: accepted, 2026-07-21.

Stochastic algorithms must be evaluated across multiple random seeds rather than by repeatedly timing one seed. The benchmark matrix therefore gains a `random_seeds` dimension while retaining `repeats` as the number of timing repetitions for each seed.

Every source experiment receives an explicit seed override. Its run ID, manifest, algorithm settings, and `resolved_config.yaml` record that effective seed. The aggregate benchmark manifest records the complete seed set and references every immutable source run.

Raw results include objective, container count, cost, occupied bounding volume, coordinate compactness, and a canonical placement signature. Summary outputs report cross-run mean, standard deviation, range, and distinct-solution count. This change is shared experiment infrastructure and does not alter the Level 1 mathematical contract.
