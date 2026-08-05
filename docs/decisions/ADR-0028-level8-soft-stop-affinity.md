# ADR-0028: Level 8 fixed-subset soft stop affinity

## Status

Accepted.

## Context

The original stop-aware beam planner assigned every compound root to exactly
one container before three-dimensional construction. Its aggregate payload and
volume checks could not predict geometric fit, exact support, stackability,
load transfer, balance, strict LIFO, or sequential replay. A capacity-feasible
assignment could therefore make a geometrically feasible subset appear to
fail merely because an item was locked to the wrong container.

## Decision

The beam planner selects a fixed container subset and produces ranked
container preferences for each declared order. Best Fit may fall back to any
container in that subset when a preferred placement is infeasible. Subset
cardinality and cost are decided by the outer search; within that fixed subset,
affinity guides candidate selection before the geometric Best-Fit score.
Preference rank never replaces the Level 1--8 feasibility policy or independent
validators.

An explicit `order_id` defines an indivisible group. Once the first item of
that order is placed, the remaining items are bound to the same container.
Legacy rows without `order_id` use `item_id` as their group identifier; items
are never implicitly grouped merely because they share a delivery stop.

The pipeline retains compact and delivery-priority candidates and selects only
after full validation, then by used-container count and cost. A planner timeout
or heuristic failure cannot invalidate an already valid baseline and is not a
proof of mathematical infeasibility.

## Consequences

- Aggregate capacity remains useful for pruning and preference generation.
- Geometry/support can trigger deterministic fallback inside the fixed subset.
- Planned and actual container use/stop fragmentation may differ and are both
  persisted with preference-hit and fallback counters.
- FFD remains unchanged as the fast comparator in this checkpoint.
- Route optimization, OSRM, OR-Tools, and Level 9 remain outside this decision.
