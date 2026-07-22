# Extreme-Point Simulated Annealing

`extreme_point_simulated_annealing` is a seeded, CPU-friendly metaheuristic shared by Levels 1 and 2 and initialized by `extreme_point_ffd`.

At each iteration it samples item-order neighbors from the shared relocate, adjacent-swap, front/back-reinsert, and container-elimination destroy-and-repair neighborhood. Each candidate is reconstructed by the fixed-orientation Extreme-Point packer and therefore still respects the active geometric and payload checks.

The current state uses Metropolis acceptance:

```text
P(accept) = exp(-(E_candidate - E_current) / temperature)
```

Improving moves are always accepted. Unlike Hill Climbing, the candidate pool may temporarily use a worse container subset, and Metropolis can accept worse count, cost, or compactness while the temperature is high. This allows the search to leave a local optimum. Temperature follows geometric cooling and never falls below `minimum_temperature`. Random choices use `project.random_seed`, so identical inputs, config, and seed reproduce the same result.

The algorithm separately retains the best lexicographic solution found by:

1. used-container count;
2. synthetic container cost;
3. occupied bounding volume;
4. coordinate compactness.

The returned result is therefore no worse than its initial FFD solution on that score. It reports only `FEASIBLE`, never `OPTIMAL`. Level 2 reconstructs every candidate with exact support checks. The method does not rotate items or claim stackability/load-bearing/physical stability.

Use `scripts/run_benchmark.py --seeds ...` to measure robustness across independent random trajectories. `--repeats` repeats each seed and is not a replacement for a seed sweep.

Main settings are under `algorithms.extreme_point_simulated_annealing`:

- `max_iterations`;
- `max_neighbors`;
- `neighbors_per_iteration`;
- `initial_temperature`;
- `cooling_rate`;
- `minimum_temperature`;
- `subset_enumeration_limit` and `subset_candidate_limit`.
