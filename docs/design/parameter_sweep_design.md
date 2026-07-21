# Parameter sweep design

The parameter-sweep runner evaluates a finite YAML Cartesian grid through the normal registry-driven experiment pipeline. Every parameter-set, instance, seed, and repeat creates an immutable source run below the active level's output directory. Overrides are written into that run's `resolved_config.yaml`; the aggregate never uses hidden notebook state or temporary source configs.

Outputs are stored below `outputs/<level>/runs/<sweep_id>/sweep/`:

- `request.json`: resolved grid dimensions and expected case count;
- `parameter_sets.csv`: stable parameter-set IDs and values;
- `results.csv`: every source experiment, seed, repeat, quality metric, signature, and error;
- `summary.csv` / `summary.json`: quality statistics across seeds and runtime across repeats;
- `ranking.csv`: deterministic ranking for each item/container scale;
- `best_parameters.json`: the rank-1 parameter set for each tested scale.

Ranking is lexicographic: success rate descending; worst/mean used-container count ascending; worst/mean/standard-deviation cost and objective ascending; mean/standard-deviation occupied bounding volume and coordinate compactness ascending; then runtime ascending. A rank-1 set is only best within the declared finite grid, instances, seeds, and metrics. It is not a proof of global algorithm-parameter optimality.

Unknown parameter names, duplicate grid values, empty dimensions, duplicate/negative seeds, and grids above `max_parameter_sets` are rejected before an aggregate run directory is created.
