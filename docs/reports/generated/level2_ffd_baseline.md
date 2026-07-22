# Level 2 FFD practical-default baseline

Generated on 2026-07-22 from suite
`config/level_02/benchmarks/ffd_baseline_local.yaml`.

- Benchmark run: `20260722T105757852456Z__level_02__benchmark__seed42`
- Status: `SUCCESS`
- FFD scenarios: 9
- Repeats per scenario: 3
- Validation success rate: 100% in every scenario
- Distinct placement signatures per scenario: 1
- Minimum exact support ratio across all FFD scenarios: 0.833333

| Scenario | Items/containers | Used containers | Mean runtime (s) |
|---|---:|---:|---:|
| exact reference prefix | 3/2 | 1 | 0.000144 |
| practical prefix | 20/5 | 2 | 0.000778 |
| stable random 101 | 20/5 | 2 | 0.009132 |
| stable random 202 | 20/5 | 2 | 0.002651 |
| stable random 303 | 20/5 | 2 | 0.004822 |
| diverse volume | 40/8 | 2 | 0.030924 |
| payload heavy | 40/8 | 5 | 0.042963 |
| volume heavy | 50/8 | 4 | 0.412345 |
| prefix scale | 100/12 | 4 | 1.626394 |

On the 3-item exact-reference instance, FFD and MILP both used one container
with objective 2061. MILP was `OPTIMAL`; FFD remained correctly labelled
`FEASIBLE`. The baseline supports promoting FFD to the Level 2 practical
default. It is not a global-optimality claim for the larger scenarios.
