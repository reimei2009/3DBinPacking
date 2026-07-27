# ADR-0021: Keep nesting relations fixed during Level 6 compound search

## Status

Accepted.

## Decision

Level 6 constructs explicit nesting relations deterministically before running
the packing search. FFD, Best Fit, Hill Climbing and Simulated Annealing receive
only compound roots. Hill/SA neighborhoods may reorder, relocate or repack
compound roots, but cannot split members or modify the nesting relation graph.

Best Fit initializes and repairs Hill/SA. Simulated Annealing uses the inherited
research profile `p006_3f888c7c` (`200`, `0.05`, `0.99`). FFD remains the
experimental default.

## Consequences

Every final solution is checked by the independent compound validator. This
checkpoint does not optimize relation selection jointly with coordinates and
does not activate EMS, MILP, internal nesting load transfer or orientation-aware
nesting.
