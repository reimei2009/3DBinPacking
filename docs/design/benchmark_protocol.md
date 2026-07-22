# Level 1 benchmark protocol

A benchmark is a controlled algorithm comparison, not a collection of unrelated
experiment runs.  A valid comparison group has all of the following in common:

- one `level_id` only;
- one named `scenario_id` with the same exact selected item IDs and container count;
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
| `small_random_i10_c3` | 10 items, 3 containers | seeded subset; MILP reference plus all methods |
| `medium_random_i20_c5` | 20 items, 5 containers | independent seeded general-quality subset |
| `diverse_volume_i40_c8` | 40 items, 8 containers | coverage across the full item-volume range |
| `payload_heavy_i40_c8` | 40 items, 8 containers | payload-stress profile |
| `volume_heavy_i100_c12` | 100 items, 12 containers | volume/scalability stress profile |

Run it with:

```powershell
python scripts/run_benchmark.py --suite config/level_01/benchmarks/core_local.yaml
```

The suite evaluates 6 methods on the small reference and 5 non-MILP methods on
the four larger profiles. With three seeds and one repeat this is
`(6 + 4 × 5) × 3 = 78` independently validated runs. MILP is deliberately not
scheduled on medium/large scenarios. For a quick check, use a small ad-hoc
matrix:

```powershell
python scripts/run_benchmark.py --level level_01 --algorithms extreme_point_ffd extreme_point_best_fit --item-counts 10 --container-counts 3 --seeds 7 11
```

Ad-hoc matrices are still grouped into generated scenarios such as
`items_10__containers_3`; named suites should be used for reported R&D results.

Every scenario records `item_selection_strategy`, optional selection seed,
the exact ordered item ID list, `selected_item_ids_checksum`, raw-source
checksum, item profile statistics, and an overall `input_fingerprint`. The
supported deterministic policies are `prefix`, `stable_random`,
`volume_stratified`, `largest_volume`, and `heaviest`.

## Reading results

Use `benchmark/summary.csv` only within one scenario/fingerprint when deciding
which algorithm is better. The runner also produces these reproducible derived
views:

- `benchmark/ranking.csv`: one Level-1 ranking per comparable group: higher
  valid-solution rate, then fewer containers, then lower cost, then lower mean
  algorithm runtime;
- `benchmark/pairwise_comparison.csv`: neutral A-versus-B deltas;
- `benchmark/pareto_frontier.csv`: methods that are not dominated jointly on
  validity, container count, cost and runtime;
- `benchmark/milp_reference_gaps.csv`: quality/runtime gaps only where the
  MILP row completed every run with `OPTIMAL` status;
- `reports/summary.md`: a human-readable summary of the above.

The Pareto frontier is exploratory: it does not replace the Level-1
lexicographic acceptance objective. MILP is the exact reference only on small
cases where it proved optimal; constructive heuristics are speed baselines;
local search and simulated annealing should be evaluated over multiple seeds.

The Streamlit **So sánh benchmark** tab now lets the user select a benchmark
run and then one comparable scenario before rendering its table and chart.

It also supports an interactive same-instance workflow: select at least two
algorithms, one item count, one container count, a shared seed list, and a
repeat count, then run the comparison directly. The dashboard prioritizes the
Level 1 lexicographic quality measures (container count, then experimental
container cost), valid-solution rate, runtime, and a runtime-versus-quality
trade-off. The composite Big-M objective remains available as diagnostic data
but is intentionally not the primary chart.
