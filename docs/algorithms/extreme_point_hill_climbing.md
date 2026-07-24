# Extreme-Point Hill Climbing

`extreme_point_hill_climbing` is a deterministic destroy-and-repair local-search
algorithm shared by Levels 1–4. Levels 1–3 retain `extreme_point_ffd` as their
default constructor and repair strategy; Level 4 uses
`extreme_point_best_fit` for both, while its feasibility policy continues to
enforce orientation, exact support, and stackability.

It uses destroy-and-repair neighborhoods over the item permutation:

- `relocate`: prioritize items from one container for reinsertion elsewhere;
- `swap`: exchange adjacent positions in the construction order;
- `reinsert`: move one item to the front or back of the order;
- `container_elimination`: try compatible subsets with fewer containers while rebuilding by extreme points.

Every neighbor is a complete fixed-orientation Extreme-Point reconstruction. Steepest strict improvement is accepted lexicographically by:

1. used-container count;
2. synthetic container cost;
3. occupied bounding volume;
4. coordinate compactness.

The search stops at a local optimum or `max_iterations`. It is not A*, does not accept worse moves, and cannot prove global optimality. Every reconstruction uses the active feasibility policy; Level 2 therefore rejects unsupported neighbors before acceptance. All returned placements pass the independent active-level validator.
