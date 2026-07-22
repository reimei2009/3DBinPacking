# Level 2 acceptance criteria

- Level 1 regression suite remains unchanged and passes.
- Level 2 data and outputs are isolated under `level_02` paths.
- Every item is assigned exactly once and passes Level 1 geometry/payload validation.
- Every above-floor item contacts at least one actual top face below it.
- Exact union support ratio meets the configured threshold.
- Every item base center is supported or the item is on the floor.
- Solver-grid support is checked independently from canonical placements.
- `support.csv` and `support_validation.json` are persisted without changing placement CSV schema.
- Manifest declares support active and full physical stability inactive.
- Rotation, stackability, load-bearing, load transfer, and loading order remain unimplemented.

