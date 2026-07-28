# ADR-0018: Model nesting as an external compound projection

Status: accepted, 2026-07-24.

## Decision

For a future active Level 6 runtime, an explicit nesting chain is externally
represented by one root compound envelope. Its height is the root height plus
declared child increments, and its external weight is the sum of member
weights. Nested children are logical members, not exceptions scattered through
the generic pairwise-overlap checker.

## Consequences

- The existing Level 5 geometry/load-transfer code remains unchanged.
- A Level 6 policy will validate boundary, overlap, support, stackability, and
  external load transfer on compounds.
- Internal forces and exact child insertion coordinates are not claimed or
  inferred; they require a later physical model and source metadata.
