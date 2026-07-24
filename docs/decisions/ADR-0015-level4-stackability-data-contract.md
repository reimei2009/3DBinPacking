# ADR-0015: Use a versioned stackability contract before enabling Level 4

Status: accepted, 2026-07-23.

## Context

The 3DBPPsi-derived raw input contains `stackability_code` and
`max_stackability`. The upstream README confirms same-code stacking but does
not define the precise semantics of the maximum value. The current observed
values are `4` and `100`; treating either code or number with unstated meaning
would make experimental results non-reproducible.

## Decision

Level 4 uses same-code compatibility directly. It models direct stack parent
relationships as a forest and adopts a versioned project convention for the
maximum: maximum layers in a parent chain including the root, with the minimum
cap along the chain. Non-stackable items are identified only by explicit
configuration, never by an inferred numeric code.

## Consequences

- Level 4 can consume the current research data now and can map a future
  operational dataset through configuration.
- Load-bearing remains inactive and cannot be inferred from stackability.
- A later verified field definition can add a new contract version without
  invalidating historical runs.
