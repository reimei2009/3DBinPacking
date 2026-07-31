# Level 8 sequential replay scale protocol

## Purpose

Measure the Level 8 post-processing replay separately from packing. This is a
research acceptance protocol, not a transport certification report.

## Required gate: 100 items

Generate `scale_1000_c80.yaml`, then run
`config/level_08/benchmarks/sequential_replay_100_manual.yaml`.

- Both cases must sample 100 rows from the 1000-row source, and prefix versus
  stable-random must have different `selected_item_ids_checksum` values.
- Both prefix and stable-random cases must be `FEASIBLE` and `VALID`.
- Replay must finish within 45 seconds.
- The two repeats must have the same placement signature, simulation plan,
  event log, and artifact checksums.
- Unloading metadata must report
  `delivery_priority_dependency_balance_aware_backtracking_v2`. If the gate fails,
  `NO_BALANCE_SAFE_REMOVAL` must identify the priority, ready items and the
  best projected longitudinal/lateral offsets.

## Bounded observation: 300 items

Use the same generated `scale_1000_c80.yaml` source, then run
`config/level_08/benchmarks/sequential_replay_300_manual.yaml`.

- Best Fit is the primary solver; FFD is a comparator.
- Prefix and stable-random seeds 101, 202, and 303 must have four distinct
  selected-item checksums, shared fairly between both algorithms.
- Every case must terminate deterministically within the 45-second pipeline
  budget as `VALID`, construction `TIME_LIMIT`, or `REPLAY_TIME_LIMIT`.
- A construction timeout is a bounded scalability observation, not a valid
  packing: it must report `delivery_repair_termination_reason:
  construction_time_limit`, suppress the objective, mark replay `SKIPPED`,
  and write no partial solution or `simulation/` artifacts.
- A replay timeout must likewise have no objective and no incomplete
  `simulation/` artifact directory.

## Evidence to record

For each source run, record `sequential_simulation_status`, replay graph/state
runtime, state count, termination reason, container count, validation status,
and simulation artifact checksums when valid. Compare the incremental engine
against the full-state fixture regression; automated tests establish equality
of step-level results on the controlled support-chain fixture.
