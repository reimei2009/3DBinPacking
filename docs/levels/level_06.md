# Level 6 — Explicit nesting (experimental)

Level 6 activates nesting only from explicit source metadata. A compatible
host–child relation produces one external compound-root envelope: the root
dimensions define its floor footprint, its effective height is the root outer
height plus child increments, and its external weight is the sum of members.

The registered experimental portfolio is:

- `extreme_point_ffd_nesting_fixture` — default experimental FFD;
- `extreme_point_best_fit_nesting_fixture` — constructive comparator;
- `extreme_point_hill_climbing_nesting_fixture` — balanced comparator;
- `extreme_point_simulated_annealing_nesting_fixture` — quality comparator
  using the locked p006 profile.

All four reuse the deterministic declared-relation policy, compound feasibility
policy, and independent compound validator. The relation graph is constructed
once before search and remains immutable. Search, neighborhood repair,
external boundary, non-overlap, support, stackability, and static load transfer
operate only on compound roots.

Internal contact forces, pressure, load distribution inside a nested chain,
orientation-aware nesting, and neighborhoods that change nesting relations
remain inactive.

## Acceptance fixtures

Depth-two chain:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_experiment.py --level level_06 --config config\level_06\experiments\declared_nesting_chain_fixture.yaml --items-count 3 --containers-count 1
```

Expected: 2 relations, 1 compound, maximum depth 2, effective height `165 mm`.

Multi-compound semantic fixture:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_experiment.py --level level_06 --config config\level_06\experiments\declared_nesting_multi_compound_fixture.yaml --items-count 4 --containers-count 1
```

Expected: 2 relations, 2 compounds, and `TOP-001` externally supported by
`ROOT-001`; the compound-root load-transfer graph has one edge.

Compare the four solvers deterministically (eight source runs only):

```powershell
.\.venv\Scripts\python.exe .\scripts\run_benchmark.py --suite config\level_06\benchmarks\compound_portfolio_fixture_local.yaml
```

The fixtures verify semantic correctness and output contracts, not production
performance or a practical-solver ranking.
