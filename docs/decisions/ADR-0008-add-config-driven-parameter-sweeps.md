# ADR-0008: Add config-driven parameter sweeps

Status: accepted, 2026-07-21.

After introducing multi-seed benchmarks, algorithm hyperparameters must be compared without manually editing Level 1 defaults or duplicating experiment configs. We add a generic parameter-sweep runner driven by a finite YAML grid.

Experiment requests may carry explicit algorithm-setting overrides and bounded config overrides. Each level pipeline merges those values into the effective configuration and persists it in the source run's resolved config. `sweep.config_parameters` supports scalar dotted paths under `model`, `support`, `solver`, and `validation`, allowing Level 2 sensitivity studies such as `support.threshold` without editing a default YAML. Aggregate sweep outputs reference all source runs and rank parameter sets independently for each tested item/container scale.

The default Level 1 sweep targets Simulated Annealing temperature, cooling rate, and iteration budget. The infrastructure is reusable by later registered algorithms and levels, but it does not add any future-level physical constraint.
