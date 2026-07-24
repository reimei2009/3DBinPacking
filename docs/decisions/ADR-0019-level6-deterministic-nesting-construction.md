# ADR-0019: Deterministic construction of explicit Level 6 nesting relations

## Status

Accepted for fixture construction only.

## Decision

Use `explicit_nesting_best_fit_chain_v1` to construct optional fixture relation
graphs from declared nesting metadata. Process eligible children in descending
outer volume, then item ID. For each child, try same-container eligible hosts
in ascending remaining declared inner volume, then item ID. A candidate is
accepted only when the canonical nesting engine validates it.

## Consequences

The result is reproducible and respects compatibility, dimensions and chain
depth without duplicating those rules. It is deliberately not an optimization
method: it does not move boxes, change orientation, reduce geometry itself, or
guarantee a maximum number of nested items. A future nesting-aware constructor
may call this policy before producing compound candidates.
