# Level 4 — Stackability rules

Status: **the data contract, stack graph schema, independent validator,
isolated pipeline, and five heuristic/metaheuristic solvers are implemented**.

Level 4 inherits the full Level 3 contract: horizontal-only orientation,
boundary, payload, non-overlap, floor contact, exact base-support area, and
base-center support. It adds the *business permission* to form vertical
stacks. It does not add load-bearing or load transfer.

## Active data semantics

The contract is stored in
[`config/level_04/stackability_rules.yaml`](../../config/level_04/stackability_rules.yaml).

- Items may be declared direct stack parent/child only when their normalized
  `stackability_code` is identical.
- `p[j,i,k] = 1` means item `j` is the unique declared direct stack parent of
  item `i` in container `k`.
- An item on the floor is a stack root. A non-floor item has one declared
  parent, so all parent relations form a forest of named stacks.
- `stack_depth` is the number of parent edges from the root; `stack_layer_count`
  includes the root layer.
- `max_stackability` is used through the versioned project convention
  `maximum_layers_in_parent_chain_including_root`. A chain cap is the minimum
  `max_stackability` found along that chain.
- `non_stackable_codes` and `non_stackable_item_ids` are explicit config
  lists. The current source does **not** document code `0` as non-stackable,
  so it is not treated specially.

The upstream project states that items assigned the same stackability code can
be stacked, but its README does not define the exact unit/semantics of
`max_stackability`. The chain-limit interpretation above is therefore a
versioned Level 4 project convention, not an unstated claim about the source.
Changing it later requires a new contract version and does not rewrite old
experiments.

## Current solver scope

`extreme_point_best_fit` is the practical default. `extreme_point_ffd` is an
active deterministic constructive comparator; `maximal_space_best_fit` is a
second constructive comparator with a maximal-empty-space representation. All
three use the same candidate policy: Level 3 exact support composed with
same-code parent selection (largest contact area, then item ID) and the
declared chain cap. The final `p[j,i,k]` records are reconstructed by the same
deterministic rule and checked again by the independent validator.

Run a small manual experiment:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_experiment.py `
  --level level_04 --algorithm extreme_point_best_fit `
  --items-count 10 --containers-count 3 --non-interactive
```

Inspect `solution/stacks.csv`, `validation/stack_validation.json`, and the
stackability object in `solution/solution.json`.

The versioned Best Fit baseline protocol is
`config/level_04/benchmarks/best_fit_baseline_local.yaml`. Run the practical
and scale matrix manually following
`docs/reports/manual/level_04_best_fit_acceptance.md`; do not run it implicitly as
part of unit testing. A separate fair FFD-versus-Best-Fit protocol is
`config/level_04/benchmarks/core_constructive_local.yaml`.

`extreme_point_hill_climbing` is the active local-search comparator. At Level
4 it starts from Best Fit and performs every destroy-and-repair neighbor using
Best Fit, while the same support/stackability policy filters candidates.

`extreme_point_simulated_annealing` is the seeded metaheuristic comparator.
At Level 4 it also initializes and repairs with Best Fit; it may temporarily
accept a worse valid neighbor, but retains the best valid packing found.

Two versioned SA sensitivity protocols under `config/level_04/sweeps/` freeze
the `prefix` and `stable_random` item-selection profiles independently. They
vary SA search parameters and seeds without changing the Level 4 constraint
contract.

## Solver portfolio

| Profile | Algorithm | Intended use |
| --- | --- | --- |
| Fast | Extreme Point Best Fit | Default interactive/local run. |
| Balanced | Hill Climbing initialized and repaired by Best Fit | Better cost/compactness when a few seconds are acceptable. |
| Quality | Simulated Annealing p006 (`200`, `0.05`, `0.99`) | Difficult profiles where lower container count can justify higher runtime. |

The three versioned experiment configs are under `config/level_04/experiments/`.
Best Fit remains the Level 4 default; selecting SA in the UI uses the p006
settings by default.

## Mathematical relationship

For distinct items `i`, `j` and container `k`:

```text
p[j,i,k] = 1  iff  j is the declared direct stack parent of i in k
```

The Level 4 validator requires a declared parent to have the same
container, vertical top-face contact, matching permitted group, and Level 3
geometric support. It uses `p` to build `stack_id`, depth, layer count,
and the path cap. `p` is not a load distribution variable.

## Source audit

The current raw `dataset_small_items_original.csv` has 501 rows:

| Field | Observed values | Contract treatment |
| --- | --- | --- |
| `stackability_code` | `0, 1, 2, 3, 4, 5, 6` | used as normalized compatibility group |
| `max_stackability` | `4` (33 rows), `100` (468 rows) | used through the versioned chain-limit convention |
| `forced_orientation` | `n`, `w` | remains Level 3's separately governed orientation field |

## Out of scope

- load-bearing capacity and load transfer;
- force/pressure distribution over support surfaces;
- fragility, nesting, balance, loading order, and unloading order;
- vertical-axis rotation;
- interpreting an undocumented source code as non-stackable.

## Acceptance status

The deterministic constructive, local-search, SA-sensitivity, and solver
portfolio protocols are versioned under `config/level_04/`. Level 4 is closed
when the portfolio protocol passes the checks in
`docs/reports/manual/level_04_best_fit_acceptance.md`.

Level 4 has no MILP implementation. A future small exact reference may be
added as a separate research checkpoint; it is not required by the current
heuristic/metaheuristic acceptance contract.
