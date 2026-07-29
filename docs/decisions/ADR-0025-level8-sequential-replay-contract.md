# ADR-0025: Freeze a deterministic sequential replay contract before simulation

Status: Accepted.

Level 8 currently validates static straight-path LIFO evidence.  A later
sequential simulation must not silently redefine that evidence, infer a route,
or turn an invalid strict-LIFO packing into a valid one through undeclared
rehandling.

Therefore the first sequential-logistics checkpoint defines only a pure,
versioned contract:

- stops are declared by existing `delivery_priority` / `delivery_stop_id` data;
- the only active policy is `strict_lifo_no_rehandling`;
- logical durations use a deterministic configured mass-linear formula, not
  wall-clock timestamps;
- future artifacts are written beneath one run's `simulation/` directory;
- future events have a fixed schema and logical sequence/time fields.

This checkpoint deliberately provides no simulation executor, route optimizer,
handling-equipment model, staging area, or physical unloading claim.  A later
engine must independently replay state transitions and revalidate the affected
Level 1--8 constraints after each removal.
