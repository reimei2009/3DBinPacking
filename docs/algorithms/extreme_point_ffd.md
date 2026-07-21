# Extreme-Point First-Fit Decreasing

`extreme_point_ffd` is a deterministic, CPU-friendly Level 1 constructive heuristic.

1. Sort fixed-orientation items by decreasing volume, maximum dimension, weight, then ID.
2. Search container subsets by minimum count and synthetic cost. Exhaustive subset enumeration is limited by `subset_enumeration_limit`; larger container sets use deterministic candidate orderings.
3. For each item, scan containers and their extreme points in bottom-left-back order `(z, y, x)`.
4. Add the three positive-axis corners of every accepted placement as new candidate points.
5. Reject candidates violating boundaries, payload, or positive-volume non-overlap.
6. Pass the completed solution through the independent Level 1 validator.

The method does not rotate items and does not model support, stacking, or physical stability. `FEASIBLE` is not an optimality guarantee. Failure is reported as `INFEASIBLE_HEURISTIC`, explicitly not a proof that the mathematical instance is infeasible.
