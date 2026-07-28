# ADR-0022: Use an explicit container balance profile for Level 7

## Status

Accepted.

## Decision

Level 7 will express horizontal center-of-mass targets and tolerances through
a versioned YAML profile, with optional overrides per physical container ID.
The first profile is `symmetric_center_band_v1`; its values are synthetic
research assumptions and carry explicit provenance.

The profile does not infer transport balance from payload capacity,
stackability, load-bearing capacity, or item mass. Item `weight_kg` and
canonical placements are the only planned inputs to the COG calculation.

## Consequences

The data contract can be validated now without registering Level 7. Floor-zone
loads, axle constraints, door clearance, dynamic loading, and vehicle physics
remain separate future contracts, avoiding an ambiguous partial interpretation
of those constraints.
