# ADR-0012: Deterministic benchmark instance profiles

Status: accepted.

The previous benchmark varied item count while always selecting `head(n)` from
the raw dataset. This was reproducible but not representative: neighboring
scales were nested prefixes and could over-represent whichever item families
occurred first in source order.

Level 1 now supports five deterministic subset policies in the canonical data
preprocessor: `prefix`, `stable_random`, `volume_stratified`,
`largest_volume`, and `heaviest`. The stable random policy ranks source rows by
SHA-256 of selection seed, source row, and item ID instead of relying on mutable
global RNG state. Each processed manifest stores exact IDs, checksums, and
profile statistics. Raw data remains immutable.

Benchmark scenarios may restrict their allowed algorithm set. The core suite
runs MILP only on the 10-item exact-reference scenario; heuristics and
metaheuristics cover medium and stress/scalability scenarios. This prevents a
nominally local suite from scheduling exact MILP on instances where its cost is
not proportionate to its role as a reference.

These changes affect experimental sampling and orchestration only. They do not
change Level 1 orientation, variables, objective, constraints, or validator.
