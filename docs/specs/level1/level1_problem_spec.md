# Level 1 problem specification

Given fixed-orientation rectangular items and one physical copy of each heterogeneous container, assign every item exactly once and choose nonnegative coordinates. Items must remain within their assigned container, have disjoint interiors, and respect payload limits. Minimize container count first and synthetic container cost second. Rotation, support, stacking, and stability are out of scope.

Implemented solution methods are exact MILP Big-M, deterministic Extreme-Point First-Fit Decreasing, Extreme-Point Hill Climbing, and seeded Extreme-Point Simulated Annealing. MILP may prove optimality; heuristic and metaheuristic methods only report `FEASIBLE` after independent validation.
