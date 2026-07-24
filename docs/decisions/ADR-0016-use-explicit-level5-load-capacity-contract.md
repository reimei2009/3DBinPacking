# ADR-0016: Use an explicit Level 5 load-capacity contract

Status: accepted, 2026-07-24.

## Context

The current 3DBPPsi-derived input contains item weight, stackability code, and
maximum stack layers, but no measured compression strength, maximum supported
load, or fragility field. Stackability is not evidence of load capacity.

## Decision

Level 5 introduces explicit `max_supported_weight_kg`, `is_fragile`, and
`load_capacity_source` attributes. Research runs initially use the versioned
synthetic profile `synthetic_weight_factor_v1`, where non-fragile capacity is
four times item weight. Overrides are explicit and provenance-bearing.

Future physical datasets must provide verified values through a new profile or
sidecar mapping. They must not silently replace or reinterpret historical
synthetic runs.

## Consequences

- The project can develop and test recursive load-transfer logic without
  claiming that synthetic values are physically safe.
- No strength value is inferred from `stackability_code` or
  `max_stackability`.
- Level 5 activation requires the load engine, independent validator, isolated
  pipeline, and solver feasibility policy; those gates are satisfied by the
  first Best Fit runtime checkpoint.
