# Level 5 solver portfolio baseline — 2026-07-24

## Provenance

- Suite: `config/level_05/benchmarks/portfolio_local.yaml`
- Benchmark run: `20260724T052509555350Z__level_05__benchmark__seeds3_10be15e3`
- Algorithms: Extreme Point Best Fit, Hill Climbing, Simulated Annealing p006.
- Seeds: `7, 11, 19`; one repeat per seed.
- Active policy: `horizontal_orientation_geometry_payload_exact_support_stackability_load_bearing`.
- Every one of the 18 source runs reported `FEASIBLE` and independent validation `True`.

## Fair-comparison checks

| Scenario | Source runs | Input fingerprints | Selected-item checksums |
| --- | ---: | ---: | ---: |
| `portfolio_prefix_i20_c5` | 9 | 1 | 1 |
| `portfolio_stable_random_101_i20_c5` | 9 | 1 | 1 |

Therefore each solver comparison in a scenario uses identical items and
containers; results are not compared across different input fingerprints.

## Results

| Scenario | Profile | Containers | Cost | Mean algorithm time |
| --- | --- | ---: | ---: | ---: |
| Prefix i20/c5 | Best Fit | 2 | 1930 | 0.024 s |
| Prefix i20/c5 | Hill Climbing | 2 | 1810 | 0.829 s |
| Prefix i20/c5 | SA p006 | 2 | 1810 | 3.433 s |
| Stable random 101 i20/c5 | Best Fit | 3 | 2950 | 0.052 s |
| Stable random 101 i20/c5 | Hill Climbing | 3 | 2780 | 2.494 s |
| Stable random 101 i20/c5 | SA p006 | 2 | 2300 | 16.915 s |

## Decision

- **Fast:** keep Best Fit as the interactive/practical default.
- **Balanced:** keep Hill Climbing, which improves cost without changing the
  prefix container count, at a modest runtime increase.
- **Quality:** keep SA p006. On the difficult frozen profile it is the only
  portfolio solver that consistently reduces the result from three to two
  containers, with the expected higher runtime.

No exact Level 5 reference exists, so these are comparative heuristic results,
not proof of global optimality. This baseline does not activate pressure,
moments, deformation, dynamic loads, or full mechanical stability.
