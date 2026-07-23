# Manual test flow

Activate the environment, list implemented choices, then run the generic experiment entrypoint:

```powershell
.\.venv\Scripts\Activate.ps1
python -m container_packing.cli list
python scripts\run_experiment.py --interactive
```

The interactive command asks for level, algorithm, item count, container count, and environment. Press Enter to accept each displayed default. Terminal output includes solver/validation status, selected containers, load summary, coordinates, dimensions, runtime, and final run directory.

By default, 20 placements are displayed. Use `--preview-limit 5`, `--preview-limit 0`, or `--json-only` when needed. Full artifacts are always stored under `outputs/<level_id>/runs/<run_id>/`.

## Level 2 support-only

Fast local smoke test:

```powershell
python scripts\run_experiment.py --level level_02 --algorithm milp_big_m --items-count 3 --containers-count 2 --non-interactive
```

Validate its run independently, then inspect `solution/support.csv` and
`validation/support_validation.json`:

```powershell
python scripts\validate_solution.py --level level_02 --run-dir outputs\level_02\runs\<run_id>
```

Run the recommended practical Level 2 heuristic:

```powershell
python scripts\run_experiment.py --level level_02 --algorithm extreme_point_ffd --items-count 20 --containers-count 5 --non-interactive
```

FFD is the configured default, so `--algorithm` may be omitted:

```powershell
python scripts\run_experiment.py --level level_02 --items-count 20 --containers-count 5 --non-interactive --preview-limit 0
```

Run the deterministic FFD promotion matrix manually:

```powershell
python scripts\run_benchmark.py --suite config\level_02\benchmarks\ffd_baseline_local.yaml
```

Run the Level 2 support-threshold sensitivity sweep manually. It runs FFD for
the same 20-item/5-container instance at $\alpha=0.80$, $0.90$, and $1.00$;
each value is repeated three times only to measure runtime and verify the
deterministic placement signature:

```powershell
python scripts\run_parameter_sweep.py --config config\level_02\sweeps\support_threshold_local.yaml
```

Read `sweep/parameter_sets.csv` for the tested $\alpha$ values,
`sweep/summary.csv` for quality/runtime, and `sweep/results.csv` for the
linked independently validated runs. Do not compare the alpha variants as if
they had identical feasible regions; the purpose is sensitivity analysis.

The suite repeats each frozen subset three times. For deterministic FFD,
identical placement signatures verify reproducibility; random experiment seeds
are not interpreted as independent search trajectories.

Run the complete Level 2 benchmark suite manually (it includes a 120-second
MILP case and therefore is not part of the quick development loop):

```powershell
python scripts\run_benchmark.py --suite config\level_02\benchmarks\core_local.yaml
```

Level 2 MILP grows rapidly. Run these expensive checks manually instead of in
the normal development loop:

For MILP runs, the terminal and `solver/solver_summary.json` show `mip_gap`,
`mip_dual_bound`, and `mip_node_count`. A nonzero gap means the incumbent is
not proven optimal even when independent validation is `VALID`.

```powershell
# Includes the slow 20-item Level 1 exact reference test
python -m pytest -q

# Level 2 scaling experiment; start at 6 before trying 8 or 10
python scripts\run_experiment.py --level level_02 --algorithm milp_big_m --items-count 6 --containers-count 3 --non-interactive
```

For a finer solver approximation, copy the Level 2 YAML to a named experiment
config and change `support.grid_x/grid_y` to 6 or 8. Keep the default immutable;
the 16×16 grid is validation diagnostic data, not another MILP.

Run a repeatable benchmark after the single-run smoke test:

```powershell
python scripts\run_benchmark.py --level level_01 --algorithms extreme_point_best_fit extreme_point_ffd maximal_space_best_fit extreme_point_hill_climbing extreme_point_simulated_annealing --item-counts 10 20 --container-counts 3 5 --seeds 7 11 19 --repeats 2
```

The total number of cases is `algorithms × item counts × container counts × seeds × repeats`. Inspect `benchmark/results.csv` for every seed/repeat and `benchmark/summary.csv` for grouped runtime, quality variation, compactness, distinct solutions, and success rate. Then inspect `ranking.csv`, `pairwise_comparison.csv`, `pareto_frontier.csv`, and (only if MILP is fully optimal) `milp_reference_gaps.csv` for the automatic interpretation.

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

Every enabled algorithm receives the exact frozen subset, seeds, and repeats
for its named scenario. Compare rows
only within the same `scenario_id` and `input_fingerprint`; scenario policy
keeps MILP on the small exact-reference case. For a quick five-profile smoke
run, override the suite algorithm list:

```powershell
python scripts\run_benchmark.py --suite config\level_01\benchmarks\core_local.yaml --algorithms extreme_point_ffd --seeds 7
```

The Streamlit
**So sánh benchmark** tab provides this scenario filter. See
`docs/design/benchmark_protocol.md` for the complete contract.

The same comparison can be launched from the Streamlit **So sánh benchmark**
tab. Choose one item/container instance, at least two algorithms, shared seeds,
and repetitions. The newly created benchmark is selected automatically and its
quality, runtime, success-rate, and trade-off views appear immediately.
