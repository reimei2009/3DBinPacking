# Level 6 — Explicit nesting data contract

Status: **experimental runtime registered; one FFD compound candidate only**.

This checkpoint adds a configurable CSV source adapter and typed nesting
capability provider, a pure nesting-chain/effective-height engine, and an
independent validator. It is registered only with one experimental FFD
compound candidate.
Items without explicit compatibility metadata remain packable by Levels 1–5;
their nesting state is `nesting_disabled_undeclared`.

See `docs/specs/level6/level6_nesting_data_contract.md` and
`config/level_06/nesting_rules.yaml`. The experimental runtime composes the
inherited external Level 5 checks over compound roots; further solver families
and physical nesting mechanics remain inactive.

The fixture-only composition API validates an explicit relation list alongside
the Level 5 validator and exports `nesting_relations.csv`, `nesting_height.csv`,
and `nesting_validation.json` through the shared run writer. It does not infer
relations from coordinates and keeps `nesting_runtime_enabled: false`.

The next runtime contract is designed as a compound projection: external
geometry sees one root envelope per nesting chain and transfers the total chain
weight through that root. See `docs/specs/level6/level6_runtime_semantics.md`.
It remains inactive until a nesting-aware feasibility policy is implemented.

An independent compound-geometry fixture validator now checks the projected
boundary, non-overlap, exact support ratio, and base-center support. It is not
connected to the Level 5 runtime or the level registry.

The fixture bundle now applies that compound validator as the external geometry
source, then evaluates stackability and load transfer on pseudo-items created
from compound roots. Raw nested child boxes do not enter these external checks.

Fixture relation construction is deterministic through
`explicit_nesting_best_fit_chain_v1`: eligible children are considered by
descending outer volume then item ID; compatible hosts are ranked by minimum
remaining declared inner volume then item ID. Every tentative relation is
revalidated by the pure nesting engine, including role, group, dimensions and
depth. This helper is not a solver and is not wired into FFD/Best Fit yet.

The fixture-only FFD adapter now uses that policy before packing the resulting
compound roots. It expands children as logical co-located members and sends the
result through the independent compound-validation bundle. It remains outside
the runtime registry, CLI and UI; its `nesting_runtime_enabled` metadata stays
`false` until a full candidate feasibility policy is implemented.

The fixture adapter now filters each compound candidate with the reused Level 5
external policy: geometry/payload, exact support plus base-center contact,
stackability and recursive load-bearing. The final independent compound bundle
still recomputes every condition and remains the acceptance authority.

The fixture adapter has an isolated output writer. It accepts only a new
`outputs/level_06/runs/<run_id>` path and writes the compound, relation, support,
stack and load artifacts plus construction-policy provenance. It is not a CLI
entry point and cannot overwrite an existing run directory.

`config/level_06/runtime_candidate.yaml` freezes the only candidate,
`extreme_point_ffd_nesting_fixture`. It is now registered as an experimental
Level 6 option through `config/level_06/experimental.yaml`, but is not a
practical default and has no large-instance acceptance baseline. It retains the
manual promotion gate before any additional solver portfolio work.

Small smoke run:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_experiment.py --level level_06 --algorithm extreme_point_ffd_nesting_fixture --items-count 2 --containers-count 2
```

Declared nesting acceptance fixture (one real `HOST-001 -> CHILD-001` relation):

```powershell
.\.venv\Scripts\python.exe .\scripts\run_experiment.py --level level_06 --config config\level_06\experiments\declared_nesting_fixture.yaml --items-count 2 --containers-count 1
```

Expect one nesting relation and one compound envelope. This fixture is synthetic
and verifies semantics only; it is not a performance benchmark.

Depth-two chain acceptance fixture:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_experiment.py --level level_06 --config config\level_06\experiments\declared_nesting_chain_fixture.yaml --items-count 3 --containers-count 1
```

Expect two declared relations, one compound envelope, maximum nesting depth 2,
and an effective compound height of `165 mm`. This is still an experimental
semantic fixture, not a practical solver benchmark.

The same chain can be run with the experimental compound Best Fit adapter:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_experiment.py --level level_06 --config config\level_06\experiments\declared_nesting_chain_best_fit_fixture.yaml --algorithm extreme_point_best_fit_nesting_fixture --items-count 3 --containers-count 1
```

Both Level 6 constructive adapters reuse the same relation policy, compound
feasibility policy and independent validation bundle. They are experimental,
not a practical default or a large-instance benchmark baseline.

Tiny deterministic comparison (four source runs only):

```powershell
.\.venv\Scripts\python.exe .\scripts\run_benchmark.py --suite config\level_06\benchmarks\constructive_chain_fixture_local.yaml
```

The suite is an output-contract and deterministic-fixture check, not a runtime
comparison from which to choose a practical solver.
