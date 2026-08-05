# Level 8 cross-level container-subset audit — 2026-07-31

## Comparable input

- Selection: prefix 20 items, seed not applicable.
- Selected-item checksum:
  `a90bb25ffedb630892d37c1c03a21c22273ac6ff79ed285ca94f9fe682ce0652`.
- Container catalog: `cross_level_container_catalog_v1`, C1--C5 exactly
  matching Levels 1--7.
- Total load: 6,228.728 kg and 24.2103128 m3.

## Reference and observed candidates

Level 7 FFD uses C3+C4, returns `VALID`, and has objective `11112.0`.
This proves aggregate geometry/payload/COG feasibility at Level 7, but it does
not prove delivery/LIFO/sequential feasibility at Level 8.

The previous Level 8 delivery pass lowered its exhaustive threshold to four
for a five-container catalog. It evaluated only representative subsets and
returned a valid four-container candidate without testing every two-container
combination.

After enabling adaptive exact-small subset search:

- all six two-container subsets with sufficient aggregate payload/volume were
  attempted, including C3+C4;
- the compact C3+C4 candidate was recovered, but it contained 13 direct LIFO
  rehandles;
- bounded fixed-container repair evaluated 961 candidates and ended at a
  local optimum without satisfying the complete Level 8 contract;
- delivery-first FFD produced a replay-valid fallback using C1+C3+C4+C5,
  objective `22194.0`, zero direct rehandles and valid sequential evidence;
- delivery-first Best Fit used five containers on this profile, so the profile
  currently recommends FFD while Best Fit remains the default on its validated
  synthetic acceptance profiles.

## Interpretation

The four-container result is no longer caused by an omitted C3+C4 subset.
It is the best deterministic candidate found by the current Level 8 portfolio
under exact support, stackability, load-bearing, final COG, strict static LIFO
and balance-safe sequential replay. It is **not** a proof that a valid two- or
three-container solution does not exist.

Low volume or payload utilization alone is not sufficient to close a
container: the surviving load after every declared removal must remain valid.
Run metadata therefore records aggregate capacity lower bounds, every attempted
small-catalog subset, construction candidates, repair termination and final
candidate selection.

## Scale gate

The comparable 50/8 smoke profile did not produce a final Level 8-valid
solution with the current bounded repair budget. Consequently the comparable
web profile remains fixed at 20/5. It must not be promoted to arbitrary 50--100
item comparison until a stronger stop-aware assignment/consolidation search
passes independent Level 1--8 validation.
