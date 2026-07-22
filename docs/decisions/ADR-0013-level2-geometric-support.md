# ADR-0013: Level 2 adds geometric support only

Status: Accepted.

Level 2 composes the fixed-orientation Level 1 MILP core with floor, grid-point
support, and base-center support. It does not activate rotation or claim full
physical stability. The 4×4 MILP grid controls model size; exact union-area
validation is authoritative and a 16×16 grid is diagnostic.

The fixed-orientation sparse builder and orchestration pipeline are shared so
future levels can add variables and validators without copying Level 1. The
constructive, local-search, and metaheuristic engines receive a composable
placement-feasibility policy. Level 2 uses exact union-area and center-support
checks during candidate generation; Level 1 retains geometry/payload checks.

After the deterministic multi-profile baseline, Extreme-Point FFD is the
Level 2 `practical_default`; MILP remains `exact_reference`. FFD failure is
reported as `INFEASIBLE_HEURISTIC` without an implicit fallback so run identity
and experimental interpretation remain reproducible.

Automatic grid refinement is intentionally disabled: it could silently run
multiple expensive MILPs. A failed exact validation remains an explicit failed
run; researchers may create a separate config with a 6×6 or 8×8 solver grid.

The Level 2 builder adds normalized per-container volume cuts, global
volume/payload cuts, and their implied integer container-count lower bound.
They are redundant valid inequalities: they strengthen the relaxation but do
not change which physical placements are feasible. HiGHS gap, dual bound, and
node count are persisted so time-limited incumbents are not mistaken for
proven optima.
