# ADR-0023: Gate Level 7 promotion through a validation-only fixture contract

## Status

Accepted.

## Decision

Freeze `level_07_fixture_validation_bundle` as the only Level 7 candidate.
It is a validation/output placeholder, not a solver and not a registered
algorithm. Its contract requires inherited independent Level 6 compound
evidence, independent COG/balance evidence, and isolated Level 7 artifacts.

## Consequences

No CLI, UI, level registry, solver portfolio, or objective changes are allowed
by this checkpoint. Best Fit and FFD cannot consume balance constraints until a
separate promotion decision follows deterministic fixture review.
