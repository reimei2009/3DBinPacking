# Level 8 soft stop-affinity gate — 2026-08-03

## Scope

Cross-level comparable data, prefix 20 items, C1--C5 catalog, Best Fit delivery
solver, strict Level 1--8 validation and required sequential replay.

## Result

- Benchmark run: `20260803T085721303270Z__level_08__benchmark__seed42`.
- Repeats: 2.
- Success rate: 1.0; every final solution was independently `VALID`.
- Determinism: one distinct solution across both repeats.
- Used containers: 4 (target gate: at most 3).
- Objective: 22194; total experimental container cost: 3830.
- Mean algorithm runtime: approximately 3.84 seconds.
- Selected construction mode: `stop_aware_fixed_subset`.

The selected affinity candidate used deterministic geometric fallback and
passed static LIFO plus sequential replay. A wider diagnostic (`beam_width=128`,
`max_plans_per_subset=64`) still used four containers, so merely increasing the
beam/candidate cap is not justified.

## Decision

The implementation checkpoint is technically valid but the 20/5 quality gate
is **not passed**. Do not run or promote the 50/8 and 100/10 gates yet. Four
containers is a valid heuristic result, not proof that three containers are
infeasible. The next research step should use bounded packing-aware assignment
repair or joint route/packing coordination, not weaken support, balance, strict
LIFO, replay, or objective reporting.
