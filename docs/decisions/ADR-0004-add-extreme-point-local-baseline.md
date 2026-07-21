# ADR-0004: Add Extreme-Point FFD as the first local heuristic baseline

Status: accepted.

The first non-exact algorithm is deterministic Extreme-Point First-Fit Decreasing. It is lightweight, requires no GPU, preserves the Level 1 fixed-orientation contract, and produces canonical placements consumed by the existing validator/reporting pipeline. It establishes a fast baseline before local search, metaheuristics, or ML methods are introduced.

The algorithm must report `FEASIBLE`, never `OPTIMAL`, and an unsuccessful search must not be described as proof of infeasibility.
