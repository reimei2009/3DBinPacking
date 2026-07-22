# Manual test flow

Activate the environment, list implemented choices, then run the generic experiment entrypoint:

```powershell
.\.venv\Scripts\Activate.ps1
python -m container_packing.cli list
python scripts\run_experiment.py --interactive
```

The interactive command asks for level, algorithm, item count, container count, and environment. Press Enter to accept each displayed default. Terminal output includes solver/validation status, selected containers, load summary, coordinates, dimensions, runtime, and final run directory.

By default, 20 placements are displayed. Use `--preview-limit 5`, `--preview-limit 0`, or `--json-only` when needed. Full artifacts are always stored under `outputs/<level_id>/runs/<run_id>/`.

Run a repeatable benchmark after the single-run smoke test:

```powershell
python scripts\run_benchmark.py --level level_01 --algorithms extreme_point_best_fit extreme_point_ffd maximal_space_best_fit extreme_point_hill_climbing extreme_point_simulated_annealing --item-counts 10 20 --container-counts 3 5 --seeds 7 11 19 --repeats 2
```

The total number of cases is `algorithms × item counts × container counts × seeds × repeats`. Inspect `benchmark/results.csv` for every seed/repeat and `benchmark/summary.csv` for grouped runtime, quality variation, compactness, distinct solutions, and success rate.

Run the Maximal Empty Spaces constructive heuristic directly:

```powershell
python scripts\run_experiment.py --level level_01 --algorithm maximal_space_best_fit --config config/level_01/experiments/maximal_space_best_fit_local.yaml --items-count 50 --containers-count 8 --environment local --non-interactive
```

Run only Simulated Annealing with its experiment config:

```powershell
python scripts\run_experiment.py --level level_01 --algorithm extreme_point_simulated_annealing --config config/level_01/experiments/extreme_point_simulated_annealing_local.yaml --items-count 50 --containers-count 8 --environment local --non-interactive
```

Run the approved local parameter grid after the multi-seed benchmark:

```powershell
python scripts\run_parameter_sweep.py --config config/level_01/sweeps/extreme_point_simulated_annealing_local.yaml
```

Inspect `sweep/ranking.csv` for all ranked sets and `sweep/best_parameters.json` for rank 1 per item/container scale. Every row in `sweep/results.csv` links to a normal independently validated experiment run.

The promoted rank-1 config is intentionally scoped to the tested 20-item/5-container instance:

```powershell
python scripts\run_experiment.py --config config/level_01/experiments/extreme_point_simulated_annealing_tuned_i20_c5_local.yaml --items-count 20 --containers-count 5 --seed 42 --non-interactive
```

## Fair Level 1 benchmark suite

For a reportable comparison, run the named suite instead of mixing unrelated
single runs:

```powershell
python scripts\run_benchmark.py --suite config\level_01\benchmarks\core_local.yaml
```

Every algorithm receives every named scenario, seed, and repeat. Compare rows
only within the same `scenario_id` and `input_fingerprint`; the Streamlit
**So sánh benchmark** tab provides this scenario filter. See
`docs/design/benchmark_protocol.md` for the complete contract.

The same comparison can be launched from the Streamlit **So sánh benchmark**
tab. Choose one item/container instance, at least two algorithms, shared seeds,
and repetitions. The newly created benchmark is selected automatically and its
quality, runtime, success-rate, and trade-off views appear immediately.
