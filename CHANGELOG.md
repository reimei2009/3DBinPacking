# Changelog

## Unreleased

- Added isolated Level 2 geometric-support config, registry contract, MILP variables, constraints, decoder metadata, and independent validator.
- Extracted reusable fixed-orientation MILP and level orchestration cores while preserving Level 1 behavior.
- Added exact support union-area validation, dense-grid diagnostics, `support.csv`, and support-specific validation output.
- Kept rotation, stackability, load-bearing, load transfer, and full physical stability inactive.
- Refactored all fixed-orientation heuristics into reusable engines with composable feasibility policies.
- Enabled Extreme Point FFD/Best Fit, Hill Climbing, Simulated Annealing, and Maximal Empty Spaces for Level 2 using exact support checks.
- Added shared algorithm defaults, Level 2 benchmark scenarios, support-candidate diagnostics, and level-aware benchmark fingerprints.
- Promoted deterministic Extreme-Point FFD to the Level 2 practical default while retaining MILP as an explicit exact-reference config.
- Added algorithm-role metadata, config-driven Streamlit defaults, a no-fallback contract, and a nine-profile reproducibility baseline.
- Added a Level 2 UI alpha override, persisted it in experiment and benchmark provenance, and added generic `config_parameters` sweeps for bounded model/solver settings.
- Added the planned Level 3 horizontal-orientation data contract; no Level 3 solver, rotation, or new constraint is active yet.
- Added a shared, pure horizontal-orientation geometry core for that planned contract; it supports only `XYZ` and `YXZ`, keeps height invariant, and does not activate Level 3 execution.
- Extended canonical placements with a backward-compatible `orientation_code`; existing Level 1--2 validation remains fixed at `XYZ`, while the shared validator is ready for a future explicit horizontal profile.
- Extracted exact base-support validation into a reusable orientation-profile-aware core and added the inactive Level 3 independent validator; Level 2 remains fixed orientation.
- Refactored Extreme-Point FFD to use a reusable orientation provider; existing levels keep `XYZ`, while the planned Level 3 provider evaluates `XYZ` and `YXZ` candidates through the same support policy.
- Registered Level 3 with isolated configuration, outputs, contract, CLI, Streamlit, exact orientation-plus-support validation, and practical FFD only.

## 0.12.0 - 2026-07-21

- Added deterministic Maximal Empty Spaces — Best Fit Decreasing for Level 1.
- Added six-way empty-space splitting, duplicate/containment pruning, and objective-aware candidate scoring.
- Extracted shared constructive item ordering and container subset utilities without changing Extreme-Point behavior.
- Registered EMS across config, CLI, notebook discovery, Streamlit, benchmark reporting, and independent validation.
- Added geometry, determinism, payload, failure-semantics, differentiating-fixture, integration, and benchmark tests.

## 0.11.0 - 2026-07-21

- Added deterministic objective-aware Extreme-Point Best Fit Decreasing for Level 1.
- Extracted shared Extreme-Point geometry, capacity checks, subset search, and construction primitives without changing FFD behavior.
- Registered Best Fit across config, CLI, notebook discovery, Streamlit, benchmark reporting, and independent validation.
- Added deterministic, compactness, payload, failure-semantics, integration, and benchmark tests.

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
