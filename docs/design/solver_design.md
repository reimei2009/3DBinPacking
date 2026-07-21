# Solver design

The exact backend is `scipy.optimize.milp`, backed by HiGHS. Constraints are accumulated as coordinate triplets and converted to CSR. Integrality and bounds are explicit arrays. Solver status maps optimal, feasible time-limit, infeasible, unbounded and error states; only a finite incumbent may be extracted, and every incumbent must pass independent validation before placement outputs are written.
