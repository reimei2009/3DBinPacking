# Level 1 benchmark protocol

A benchmark is a controlled algorithm comparison, not a collection of unrelated
experiment runs.  A valid comparison group has all of the following in common:

- one `level_id` only;
- one named `scenario_id` with the same ordered item prefix and container count;
- the same raw-item checksum, container definition, and active model contract;
- the same set of random seeds and repetitions;
- one resolved experiment configuration and recorded algorithm settings.

`input_fingerprint` is written to every raw and summary row. It hashes the
Level, scenario, source data checksum, configured containers, and active model
settings. Rows with different fingerprints are not directly comparable even if
their item/container counts happen to look alike.

## Named suite

The canonical local protocol is
`config/level_01/benchmarks/core_local.yaml`. It compares all registered Level
1 methods on every scenario below:

| Scenario | Scale | Purpose |
| --- | --- | --- |
| `small_i10_c3` | 10 items, 3 containers | exact MILP reference |
| `medium_i20_c5` | 20 items, 5 containers | default Level 1 comparison |
| `large_i40_c8` | 40 items, 8 containers | local CPU scalability |

Run it with:

```powershell
python scripts/run_benchmark.py --suite config/level_01/benchmarks/core_local.yaml
```

The suite runs `algorithms × scenarios × seeds × repeats` cases. The current
suite is `6 × 3 × 3 × 1 = 54` independently validated experiment runs, so it
can take time when the exact MILP is evaluated. For a quick check, use a small
ad-hoc matrix:

```powershell
python scripts/run_benchmark.py --level level_01 --algorithms extreme_point_ffd extreme_point_best_fit --item-counts 10 --container-counts 3 --seeds 7 11
```

Ad-hoc matrices are still grouped into generated scenarios such as
`items_10__containers_3`; named suites should be used for reported R&D results.

## Reading results

Use `benchmark/summary.csv` only within one scenario/fingerprint when deciding
which algorithm is better. Compare success rate, used-container count, cost,
utilization/compactness, and runtime together. MILP is the exact reference on
small cases; constructive heuristics are speed baselines; local search and
simulated annealing should be evaluated over multiple seeds.

The Streamlit **So sánh benchmark** tab now lets the user select a benchmark
run and then one comparable scenario before rendering its table and chart.

It also supports an interactive same-instance workflow: select at least two
algorithms, one item count, one container count, a shared seed list, and a
repeat count, then run the comparison directly. The dashboard prioritizes the
Level 1 lexicographic quality measures (container count, then experimental
container cost), valid-solution rate, runtime, and a runtime-versus-quality
trade-off. The composite Big-M objective remains available as diagnostic data
but is intentionally not the primary chart.
