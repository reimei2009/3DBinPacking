# ADR-0017: Require explicit nesting compatibility metadata

Status: accepted, 2026-07-24.

## Decision

Level 6 will not infer nesting from outer geometry or `nesting_height_mm`
alone. A source must declare compatibility group, role, host inner dimensions,
maximum depth, child increment height, and provenance before a nesting relation
is active. Missing metadata disables nesting for that item without preventing
Levels 1–5 from processing the source.

## Consequences

- The public 3DBPPsi field remains preserved/inactive.
- New company CSV sources use a YAML column mapping and can preserve extra
  columns without changing raw data.
- Future Level 6 solver and validator consume one typed capability provider.
