# Level 2 data specification

Level 2 uses the same immutable raw source and fixed-orientation item/container
schema as Level 1. Preparation is repeated deterministically into
`data/processed/level_02/`; Level 1 processed files and outputs are never used
as hidden inputs.

Identity, dimensions, weight, selection order, and inclusion flag are active.
`nesting_height`, `stackability_code`, `forced_orientation`, and
`max_stackability` are preserved but inactive. Rotation, nesting,
stackability, and load-bearing fields do not affect Level 2.

Additional output is written to `solution/support.csv`; canonical
`placements.csv` is unchanged. Each row records floor state, actual supporting
item IDs, exact union support area/ratio, dense-grid diagnostic ratio, and
center-support status.

