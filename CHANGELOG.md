# Changelog

## 0.10.0 - 2026-07-21

- Raised default item opacity from 0.72 to 0.92 for clearer solid geometry.
- Added Solid, Balanced, and X-Ray display presets plus a manual opacity slider.
- Added per-item highlighting, dimming, details, and hide/show controls without mutating solution data.
- Changed the default 3D view from combined containers to the first used container.

## 0.9.0 - 2026-07-21

- Added Vietnamese-first UI text with an English language switch.
- Added localized Level contracts containing LaTeX notation, decision variables, objective, and every MILP constraint family.
- Added explicit code mappings from each mathematical expression to the canonical Level 1 implementation.
- Localized Plotly hover text, utilization labels, and Level 1 visualization warnings.

## 0.8.0 - 2026-07-21

- Added a versioned, backend-neutral `scene.json` contract and reusable Plotly 3D renderer.
- Added structured level contracts for objectives, variables, constraints, assumptions, and limitations.
- Added a thin Streamlit R&D interface over the existing application pipeline and isolated run history.
- Added generated combined/per-container HTML views without moving optimization logic into the UI.

## 0.7.0 - 2026-07-21

- Added config-driven, multi-seed parameter sweeps with immutable source experiment runs.
- Added algorithm-setting overrides that are captured in every source run's resolved config and diagnostics.
- Added per-instance robust ranking, parameter-set manifests, compactness statistics, and best-parameter exports.

## 0.6.0 - 2026-07-21

- Added benchmark seed sweeps with separate timing repeats per seed.
- Propagated seed overrides into algorithm settings, run IDs, manifests, and resolved experiment configs.
- Added cross-seed objective, container, cost, compactness, runtime, and distinct-solution statistics.

## 0.5.0 - 2026-07-21

- Added seeded `extreme_point_simulated_annealing` for reproducible local metaheuristic experiments.
- Reused the shared Extreme-Point destroy-and-repair neighborhoods and retained the best lexicographic solution.
- Added Metropolis acceptance, configurable cooling, algorithm diagnostics, tests, and benchmark integration.

## 0.4.0 - 2026-07-21

- Added deterministic `extreme_point_hill_climbing`, initialized from the greedy Extreme-Point solution.
- Added relocate, swap, reinsert, and container-elimination destroy-and-repair neighborhoods.
- Added lexicographic acceptance by container count, cost, occupied bounding volume, and coordinate compactness.
- Added regression evidence where local search reduces a fixture from three containers to two.

## 0.3.0 - 2026-07-21

- Added deterministic `extreme_point_ffd` for Level 1 with subset selection, fixed-orientation extreme points, payload and collision checks.
- Added a shared Level 1 algorithm executor so exact and heuristic methods reuse preparation, validation, reporting, CLI, and benchmark orchestration.
- Kept heuristic `FEASIBLE` distinct from MILP `OPTIMAL` and documented heuristic failure as non-proof of infeasibility.

## 0.2.0 - 2026-07-21

- Added output schema versioning, resolved-config and source-tree checksums, Git dirty state, artifact roles, and structured JSONL logs.
- Reduced solver summary duplication while retaining canonical/export/derived artifacts.
- Added a registry-driven, level-isolated benchmark runner with raw and aggregated comparisons.
- Removed the obsolete fixed-count `prepare_level1_data.py` implementation.

## 0.2.0 - 2026-07-20

- Removed fixed 20-item/5-container assumptions from preparation and solve pipelines.
- Added `--items-count`, `--containers-count`, and `--interactive` inputs to scripts/CLI.
- Added dynamically named CSVs, manifests, per-instance outputs, and logs.
- Added notebook input controls and deterministic synthetic container extension.

## 0.1.0 - 2026-07-20

- Implemented the complete Level 1 sparse MILP, CLI, validation, reporting, tests, and reproducible data preparation.
- Explicitly excluded rotation, stacking, support, and stability constraints.
