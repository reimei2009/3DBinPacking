# Extreme-Point First-Fit Decreasing

`extreme_point_ffd` is a deterministic, CPU-friendly constructive heuristic shared by Levels 1 and 2.

1. Sort fixed-orientation items by decreasing volume, maximum dimension, weight, then ID.
2. Search container subsets by minimum count and synthetic cost. Exhaustive subset enumeration is limited by `subset_enumeration_limit`; larger container sets use deterministic candidate orderings.
3. For each item, scan containers and their extreme points in bottom-left-back order `(z, y, x)`.
4. Add the three positive-axis corners of every accepted placement as new candidate points.
5. Reject candidates through the active level feasibility policy.
6. Pass the completed solution through the independent active-level validator.

Level 1 checks fixed-orientation geometry and payload. Level 2 additionally checks exact union-area and center support for every candidate. The method does not rotate items or claim physical stability. `FEASIBLE` is not an optimality guarantee. Failure is reported as `INFEASIBLE_HEURISTIC`, explicitly not a proof that the mathematical instance is infeasible.
