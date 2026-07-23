# ADR-0014: Restrict Level 3 to horizontal orientation

Status: accepted, 2026-07-23.

## Context

Level 2 is a fixed-orientation support model. The raw source includes a
`forced_orientation` field with values `n` and `w`, but this repository has no
verified source mapping for the two labels. The upstream project describes
rotation on the horizontal plane while preserving the z axis.

## Decision

Level 3 will model only `XYZ` and `YXZ`: it can swap length and width but will
not place height on a horizontal axis. Before a verified source mapping exists,
the raw label remains preserved/inactive and an explicit synthetic orientation
profile provides each allowed set.

## Consequences

- Level 3 composes safely with Level 2 because support footprints use the
  selected horizontal dimensions.
- Future stackability/load-bearing contracts continue to use a consistent
  vertical axis.
- A later source-verified mapping is an additive, versioned transformation and
  cannot silently change historical experiment results.
