# Level 7 — Container center of mass and balance (design checkpoint)

Level 7 has a data contract at
`docs/specs/level7/level7_balance_data_contract.md` and a versioned YAML profile
at `config/level_07/balance_rules.yaml`.

The pure COG engine, independent balance validator, Level 6 composition bundle,
and isolated fixture writer are available only for small fixtures. No Level 7
runtime is registered. Existing Level 1–6 behavior, objectives, solvers,
validators, CLI/UI choices, and outputs are unchanged.

The validation-only candidate contract is frozen in
`config/level_07/runtime_candidate.yaml`; it is not an executable Level 7
experiment.

The next implementation checkpoint may test the frozen acceptance fixture twice
for deterministic artifacts before any decision to register a runtime or port a
constructive solver.
