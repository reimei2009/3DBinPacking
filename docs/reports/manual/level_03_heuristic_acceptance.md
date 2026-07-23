# Level 3 heuristic acceptance procedure

This procedure freezes the practical baseline before adding a Level 3 MILP
orientation reference. It compares only algorithms operating under the same
Level 3 orientation and exact-support contract.

## Run

From the repository root with the virtual environment active:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_benchmark.py `
  --suite config\level_03\benchmarks\core_heuristics_local.yaml
```

The run prints one benchmark directory below
`outputs/level_03/runs/<benchmark_id>/`. Do not combine rows from a different
benchmark directory or a different `input_fingerprint`.

## Acceptance checks

Open `benchmark/results.csv`, `benchmark/summary.csv`,
`benchmark/ranking.csv`, and `benchmark/pareto_frontier.csv`.

| Check | Expected result |
| --- | --- |
| Contract | All rows have `level=level_03`, `orientation_profile=horizontal_rotatable`, and `feasibility_policy=horizontal_orientation_geometry_payload_exact_support`. |
| Validity | Every completed row has `success=True`, `validation_valid=True`, and `minimum_exact_support_ratio >= support_threshold`. |
| Fairness | For a given `scenario_id`, all compared algorithms share one `input_fingerprint` and `selected_item_ids_checksum`. |
| Reproducibility | Repeats with the same scenario, algorithm and seed have one `placement_signature` and one objective value. |
| Runtime | Compare `algorithm_runtime_mean_seconds`; do not call a slower method worse without also comparing container count, cost and compactness. |
| Quality | Prioritize `used_containers_mean`, then total cost, then occupied bounding volume/compactness. |

If any result is not valid, inspect its linked `experiment_run_dir`, especially
`validation/support_validation.json`, `validation/violations.csv`, and
`solver/solver_summary.json`. Do not use an invalid result in the ranking.

## Record

Copy the benchmark directory path and summarize the winning method per
scenario in a generated report. Keep generated benchmark artifacts under
`outputs/`; do not commit them as source documentation.
