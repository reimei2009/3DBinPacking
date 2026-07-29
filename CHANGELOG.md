# Changelog

## Unreleased

- Completed the sequential fixture evidence bundle with per-stop summaries,
  logical-duration metrics, and independent timeline/order validation.

- Registered the CLI-only Level 8 sequential replay fixture. Its `validate`
  path rebuilds the plan from the input snapshot and detects altered simulation
  artifacts; Streamlit remains limited to delivery-aware packing solvers.

- Added a deterministic Level 8 fixture planner and isolated sequential writer.
  It emits a validated logical-time plan, loading/unloading CSVs, and JSONL
  events without activating a generic simulator or route optimizer.

- Added the Level 8 fixture callback that independently recomputes the full
  Level 1--7 bundle after every accepted removal. Surviving nesting relations
  are filtered; support, stackability, load transfer, and COG are rebuilt.

- Added a pure Level 8 sequential removal dependency graph and fixture
  validator. It records door/support/nesting precedence and rechecks remaining
  geometry and static LIFO state after each removal; no event runtime is active.

- Added the Level 8 sequential-logistics replay data contract: deterministic
  event vocabulary, strict-LIFO/no-rehandling policy, logical timing formula,
  and isolated future `simulation/` artifacts. No simulator or solver behavior
  is activated by this checkpoint.

- Exposed Level 8's experimental delivery-aware Best Fit and FFD solvers in
  Streamlit using the tracked three-stop demo. Frozen fixture and expected-
  invalid algorithms remain CLI-only.

- Enforced the Level 8 delivery pipeline deadline across construction and
  repair. Extreme-Point Best Fit/FFD stop at the shared monotonic deadline;
  construction timeout returns `TIME_LIMIT`, no comparable objective, and no
  hidden repair phase.

- Replaced Level 8 full priority-order reconstruction with bounded local
  delivery repair. It uses blocker contributors, relocation, transfer, swap,
  and support-closure moves under one real pipeline deadline; invalid results
  continue to suppress comparable objectives.

- Promoted Level 8 to a CLI-only config-driven experimental runtime with
  delivery-aware Best Fit as primary and FFD as a first-fit comparator. Each
  run now persists delivery priority/stop distributions with the independent
  Level 1–8 validation bundle.

- Added the final controlled Level 8 three-stop/two-container acceptance
  fixture. It proves deterministic delivery-aware Best Fit and FFD evidence
  against an intentionally LIFO-invalid baseline without opening arbitrary
  input support or changing the optimization objective.

- Added a CLI-only Level 8 delivery-aware FFD fixture. It retains first-fit
  container selection and ranks only feasible candidate positions inside that
  first container by prospective direct rehandles/LIFO blockers.

- Added a Level 8 CLI-only multi-container FFD negative control. It records
  canonical first-feasible-container behavior when a later container would
  avoid a LIFO violation, before any delivery-aware FFD policy is introduced.

- Added a deterministic Level 8 two-stop/two-container Best Fit fixture. It
  verifies isolated per-container COG/LIFO evidence and delivery-aware A/B
  behavior before any arbitrary-instance or FFD expansion.

- Added CLI-only Level 8 Best Fit delivery/LIFO A/B fixtures. The aware
  candidate tie-break reduces prospective direct rehandles only after the
  existing container-count/cost priorities and inherited hard constraints;
  the ordinary Best Fit baseline is retained as expected-invalid evidence.

- Registered the Level 8 CLI-only composed validation fixture. It validates the
  inherited Level 1--7 bundle and static delivery/LIFO evidence in one isolated
  run, without a packing solver or Streamlit exposure.

- Preserved the best inherited-feasible placement between Level 7 local repair,
  adaptive LNS and controlled rescue instead of restarting each phase from the
  compact baseline. Phase-by-phase COG violations are now explicit metadata.
- Split Level 7 scale acceptance into a deterministic two-repeat Best Fit
  primary suite and a one-repeat FFD comparator suite, with an artifact-only
  baseline report builder and explicit promotion gates.
- Added artifact-only Level 7 scale-failure diagnosis with per-axis excess,
  mass-shift direction, contributor evidence, and repair-operator
  classification.
- Changed Level 7 LNS neighborhood selection to prioritize compound support
  closures by directional mass-moment contribution on the violated COG axis.
- Added adaptive Level 7 LNS neighborhoods, duplicate-candidate suppression,
  a 45-second total pipeline budget, controlled one-container rescue and a
  bounded consolidation pass with explicit outcome classes.

- Promoted Level 7 to an experimental dynamic balance runtime in Streamlit and
  CLI. Balance-aware Best Fit and First Fit now accept configured item/container
  counts and selection profiles, while frozen A/B fixture algorithms remain
  CLI-only regression evidence. The primary objective is unchanged; COG is a
  construction tie-break and final independent validation.

- Reworked dynamic Level 7 construction into a two-stage pipeline: compact
  Level 6-style baseline first, then bounded fixed-container balance repair.
  Invalid candidates now suppress the comparable objective value.

- Replaced Level 7's repeated full-solution rebuild repair with a deadline-aware
  local COG engine. It caches per-container mass/moments, targets high-impact
  compound roots, preserves support closures, evaluates relocation/swap/partial
  repack candidates, and only then permits one extra container.

- Added the Level 7 hybrid balance-repair stage: after the compact baseline and
  a short local phase, deterministic LNS destroys and re-packs only a bounded
  neighborhood in the most unbalanced containers and one donor. The default
  time budget is now 8 seconds local, 17 seconds LNS, then 5 seconds for the
  optional extra-container fallback.

- Added Level 7 manual scale-acceptance protocol, isolated acceptance assessor,
  and explicit strict versus one-extra-container execution profiles.

- Added the Level 8 explicit delivery-priority/stop data contract, configurable
  straight-path LIFO geometry primitives, semantic CSV fixture, and deterministic
  synthetic-data profiles up to 5000 items / 200 containers. Level 8 has no
  registered runtime, solver, changed objective, or generated benchmark in this
  checkpoint.

- Added an independent Level 8 static unload/LIFO validator and isolated
  fixture-evidence writer for accessibility, direct rehandles, and validation
  artifacts; Level 8 remains unregistered and solver-free.

- Added CLI-only Level 7 First-Fit balance A/B fixtures. The COG-aware variant
  retains the first feasible container and applies prospective COG ranking only
  to candidates inside that container; canonical FFD remains unchanged for
  Levels 1â€“6 and for the Level 7 baseline comparator.

- Recorded the Level 7 three-profile balance-scoring acceptance baseline:
  left-heavy discriminator, right-heavy direction check, and symmetric bias check.

- Added right-heavy and symmetric Level 7 balance acceptance profiles to verify
  that prospective COG scoring reverses direction correctly and does not add a
  needless bias when geometry and mass are symmetric.

- Added a CLI-only Level 7 canonical Best Fit baseline comparator on the balance
  discriminator fixture, establishing A/B evidence for prospective COG scoring.

- Added the CLI-only Level 7 experimental balance-aware Extreme Point Best Fit
  fixture. It uses prospective center-of-mass scoring solely as a constructive
  tie-break and requires independent final balance validation.

- Registered Level 7 as a CLI-only frozen acceptance fixture for compound-root
  center-of-mass and balance validation. It returns `VALIDATION_ONLY`, writes
  isolated evidence, supports independent re-validation, and is hidden from
  Streamlit; it does not add a practical solver or objective.

- Added Level 7's inactive, versioned container center-of-mass and horizontal
  balance data contract. It includes explicit target/tolerance provenance and
  per-container overrides but does not register a runtime or change Levels 1–6.
- Added a pure Level 7 mass-weighted center-of-mass engine and independent
  balance validator for synthetic fixtures; neither is connected to a solver
  or runtime yet.
- Added a fixture-only Level 7 composition bundle that appends independent COG
  evidence to the inherited Level 6 compound support, stackability, and
  load-transfer evidence.
- Added an isolated Level 7 fixture output writer for COG/balance evidence and
  a frozen CLI-only candidate contract with completed manual-review provenance.
- Added the Level 6 experimental compound-root Hill Climbing and Simulated
  Annealing portfolio. Both keep deterministic nesting relations immutable and
  search only over compound roots; FFD remains the experimental default.
- Added a configurable CSV source adapter and the Level 6 explicit nesting
  data contract; nesting remains inactive until declared compatibility data and
  a future runtime integration are implemented.
- Added the Level 6 pure explicit-nesting chain/effective-height engine and
  independent relation validator; no Level 6 solver or geometry relaxation is
  active.
- Added fixture-only composition of Level 5 and Level 6 nesting validation,
  including isolated nesting relation/height artifacts through the shared writer.
- Defined the inactive Level 6 compound nesting projection contract for future
  geometry, support, stackability, and external load-transfer composition.
- Added an independent Level 6 compound geometry fixture validator for projected
  bounds, non-overlap, exact support, and base-center support.
- Switched the Level 6 fixture bundle to compound geometry/support and compound
  stackability/load-transfer validation without activating a solver runtime.
- Added deterministic fixture-only Level 6 nesting relation construction using
  explicit metadata, best-fit host ranking, and canonical chain validation;
  no nesting-aware solver is active yet.
- Added a fixture-only nesting-aware FFD adapter that packs compound roots then
  validates expanded logical members through independent compound validation.
- Added a fixture-only Level 6 compound candidate policy that reuses Level 5
  exact support, stackability and load-bearing checks during FFD construction.
- Added an isolated Level 6 fixture FFD output writer with compound-validation
  artifacts and nesting-construction provenance; no Level 6 CLI/UI exists.
- Frozen a typed Level 6 runtime-candidate contract, isolated output schema and
  deterministic acceptance fixture gate before any registry/CLI/UI promotion.
- Registered the single Level 6 compound-root FFD candidate as experimental,
  with no practical default, additional solver portfolio, or large benchmark.
- Added a tracked Level 6 explicit host-child CSV fixture, source mapping and
  small experiment config for observable nesting acceptance evidence.

- Activated the isolated Level 5 runtime with Extreme Point Best Fit, recursive
  contact-area load transfer, candidate load-bearing feasibility, and final
  independent validation.
- Enabled deterministic Extreme Point FFD as a Level 5 constructive comparator
  through the same recursive load-bearing feasibility policy; Best Fit remains
  the practical default.
- Enabled Best-Fit-initialized Hill Climbing as the Level 5 local-search
  comparator through the same recursive load-bearing feasibility policy.
- Enabled seeded Simulated Annealing as the Level 5 quality comparator using
  the same Best-Fit initialization/repair and load-bearing policy.
- Added frozen prefix and stable-random Level 5 SA sensitivity-sweep protocols.
- Promoted SA p006 as the Level 5 quality profile and added fast/balanced/quality
  experiment configs plus a portfolio acceptance protocol.
- Recorded the validated 18-run Level 5 portfolio baseline: Best Fit is fast,
  Hill Climbing is balanced, and SA p006 reduces the difficult frozen profile
  from three to two containers.
- Added Level 5 load-bearing/load-transfer solution artifacts, validation
  document, manifest/metrics metadata, CLI/UI registry support, and regression
  tests while preserving Levels 1–4.

- Promoted stackability-aware Extreme Point Best Fit to the Level 4 practical default; FFD remains a deterministic constructive comparator.
- Enabled stackability-aware Maximal Empty Spaces Best Fit as a Level 4 constructive comparator.
- Refactored construction/repair strategies and enabled Best-Fit-initialized Hill Climbing as the Level 4 local-search comparator.
- Enabled Best-Fit-initialized Simulated Annealing as the seeded Level 4 metaheuristic comparator.
- Added profile-aware parameter-sweep provenance and Level 4 Simulated Annealing sensitivity protocols.
- Promoted SA p006 to the Level 4 quality profile and added versioned fast/balanced/quality portfolio configs.
- Added the Level 5 load-bearing data contract with explicit strength provenance and a documented synthetic research profile.
- Added a pure Level 5 contact-area load-transfer engine and independent validator for recursive load conservation, capacity overload, and fragile-item violations.

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
- Added a Level 3 FFD baseline suite with deterministic signature/orientation checks and orientation-aware benchmark provenance.
- Ported Extreme Point Best Fit to the Level 3 horizontal-orientation provider and exact-support policy as an alternative deterministic constructive solver.
- Ported Extreme Point Hill Climbing to reuse the Level 3 horizontal-orientation provider through every destroy-and-repack neighborhood.
- Ported seeded Extreme Point Simulated Annealing to Level 3, preserving horizontal orientation and exact support through each sampled neighborhood.
- Ported Maximal Empty Spaces Best Fit to Level 3 with horizontal orientation candidates and exact support checks at empty-space origins.
- Added a manual, fair Level 3 five-method heuristic acceptance suite and reporting procedure before the exact MILP reference stage.
- Added a small-instance Level 3 MILP Big-M orientation reference with binary `XYZ`/`YXZ` selection, orientation-dependent bounds/non-overlap/support grid, independent exact-support validation, and a five-item execution guard.
- Added the Level 4 stackability data contract, source audit, versioned same-code compatibility rule, explicit non-stackable policy, and stack-graph output contract; load-bearing remains inactive.
- Added standalone Level 4 stack graph schemas and an independent validator for declared direct parents, same-code compatibility, explicit non-stackable policy, and versioned stack-layer caps.
- Added Level 4 stack metadata exports for `solution.json`, `stacks.csv`, Markdown reports, validation documents, and backend-neutral scene item metadata.
- Registered Level 4 with an isolated config/output pipeline and a composable feasibility policy combining Level 3 exact support with same-code stack parent selection and stack-layer caps; Level 4 has no MILP implementation.

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
