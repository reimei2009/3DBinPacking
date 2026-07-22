# Level 2 mathematical model

Level 2 retains the Level 1 variables $u_k,a_{ik},x_i,y_i,z_i,\delta_{ijkd}$,
constraints R1–R9, and objective:

$$
\min\;B\sum_k u_k+\sum_k c_k u_k.
$$

For solver grid $G_x\times G_y$, threshold $r$, and
$N_{min}=\lceil rG_xG_y\rceil$, add:

$$
f_{ik}\in\{0,1\},\quad s_{ijkpq}\in\{0,1\},\quad c_{ijk}\in\{0,1\},\qquad i\ne j.
$$

Here $f$ denotes floor contact, $s$ denotes one supported base-grid point, and
$c$ denotes support of the base center. Activations are linked to both item
assignments. An active support requires:

$$
z_i=z_j+h_j
$$

and the corresponding point of item $i$ to lie in item $j$'s top-face
footprint. Each point is counted at most once. Coverage and center constraints
are:

$$
G_xG_y f_{ik}+\sum_{j\ne i,p,q}s_{ijkpq}\ge N_{min}a_{ik},
$$

$$
f_{ik}+\sum_{j\ne i}c_{ijk}\ge a_{ik}.
$$

The default 4×4 grid and 0.80 threshold require 13 points. This is a MILP
approximation, not proof of 80% physical contact area. Final acceptance uses
exact rectangle-union area from canonical placements.

The implementation also adds redundant valid inequalities to strengthen the
LP relaxation without changing the Level 2 feasible set. For item volume
$v_i$ and container volume $V_k$:

$$
\sum_i \frac{v_i}{V_k}a_{ik}\le u_k.
$$

Global volume and payload capacity inequalities, plus the implied integer
lower bound on $\sum_k u_k$, are added explicitly. These cuts help HiGHS reason
about container activation; they do not require or encourage compact visual
placement. Solver reports persist the incumbent objective, dual bound,
relative MIP gap, and explored node count when HiGHS provides them.

Canonical implementation:

- shared R1–R9 builder: `models/common/fixed_orientation_milp.py`;
- Level 2 indices and support constraints: `models/level_02/`;
- reusable heuristic feasibility policies: `algorithms/feasibility.py`;
- pure exact support geometry: `geometry/support.py`;
- independent exact validator: `levels/level_02_validation.py`.
