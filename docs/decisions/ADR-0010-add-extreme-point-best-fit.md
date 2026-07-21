# ADR-0010: Add objective-aware Extreme-Point Best Fit

Status: accepted.

Level 1 needs a second constructive baseline before adding more expensive search families. Best Fit reuses the validated Extreme-Point feasibility core but evaluates every feasible candidate instead of accepting the first one. Its lexicographic score reflects the active Level 1 objective first, then residual capacity and geometric compactness.

Shared geometry, boundary, payload, overlap, point-update, subset-search, and item-ordering logic lives in `extreme_point_core.py`. FFD and Best Fit provide separate placement-selection policies over that core. This prevents divergent feasibility implementations while keeping both algorithms independently selectable and benchmarkable.

Best Fit reports only `FEASIBLE`; it does not change the Level 1 mathematical contract and does not activate rotation, support, stacking, or stability.
