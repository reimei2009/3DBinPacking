# Level 1 exact MILP mathematical model

Sets: items `I`, containers `K`, pairs `P={(i,j):i<j}`, and six separation directions `D`.

Variables are binary use `u[k]`, binary assignment `a[i,k]`, continuous nonnegative `x[i],y[i],z[i]`, and binary `delta[i,j,k,d]`. With `B=1+sum(cost)`, minimize `B*sum(u)+sum(cost*u)`.

Constraints enforce: `sum_k a[i,k]=1`; `a[i,k]<=u[k]`; three fixed-orientation boundary inequalities activated by assignment; payload capacity; each delta implies both assignments; co-located pairs activate at least one of six directions; and each direction activates its corresponding Big-M separation inequality. `Mx=max L`, `My=max W`, `Mz=max H`. The implementation uses CSR sparse matrices.

For 20 items and 5 containers: 5 use + 100 assignment + 60 coordinate + 5700 delta = 5865 variables; 18475 constraints.

This formulation is implemented by `milp_big_m`. FFD, Hill Climbing, and Simulated Annealing do not build these variables or constraints; they construct candidate placements and send the final solution through the same independent Level 1 validator.
