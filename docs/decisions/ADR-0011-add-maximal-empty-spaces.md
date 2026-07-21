# ADR-0011: Add Maximal Empty Spaces Best Fit

Status: accepted.

After two Extreme-Point constructive policies, Level 1 needs a different geometric representation before adding heavier search methods. Maximal Empty Spaces represents usable residual cuboids explicitly, so it can discover placements that the current Extreme-Point candidate set misses while remaining deterministic and CPU-friendly.

Shared item ordering, container ordering, and subset enumeration live in `constructive_common.py`. EMS-specific splitting, pruning, feasibility checks, statistics, and state live in `maximal_space_core.py`; its selection policy lives in `maximal_space_best_fit.py`. The final placement remains the canonical solution and must pass the existing independent validator.

We accept overlapping maximal spaces because six-way splitting naturally produces them and containment pruning alone preserves more placement opportunities. Every candidate is therefore checked against actual placements, preventing invalid overlap. We do not impose an undocumented space-count cap; runtime and active-space counts are measured and reported instead.

EMS reports only `FEASIBLE`. It does not change the Level 1 mathematical contract or activate rotation, support, stacking, or stability.
