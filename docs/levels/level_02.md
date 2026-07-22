# Level 2 — Geometric support constraints

Level 2 inherits every fixed-orientation geometry, assignment, payload, and
lexicographic objective rule from Level 1. It additionally requires each item
to be on its container floor or supported by top faces below it.

Active additions are floor contact, minimum supported base ratio, and support
of the base center. The MILP approximates the base using a configurable grid;
the independent validator recomputes the exact union area of contact
rectangles. Exact validation is authoritative.

Rotation, stackability codes, load-bearing strength, load transfer, fragility,
center of gravity, loading/unloading order, and full physical stability remain
inactive. A valid result may only be described as:

> A geometry, payload, and base-support-feasible solution under Level 2 assumptions.

Level 2 supports `milp_big_m` as the exact reference plus Extreme-Point FFD,
Extreme-Point Best Fit, Hill Climbing, Simulated Annealing, and Maximal Empty
Spaces Best Fit. The five reusable engines receive an exact-support feasibility
policy; the independent validator still recomputes support from final canonical
placements.

`extreme_point_ffd` is the practical default. It stops transparently with
`INFEASIBLE_HEURISTIC` when construction fails and never silently falls back.
`milp_big_m` has the `exact_reference` role and remains directly selectable.

Redundant aggregate volume/payload cuts and a derived container-count lower
bound strengthen the MILP relaxation without changing this contract. A
`FEASIBLE_TIME_LIMIT` result remains a valid incumbent, not a proven optimum;
inspect `mip_gap` and `mip_dual_bound` in `solver/solver_summary.json`.
