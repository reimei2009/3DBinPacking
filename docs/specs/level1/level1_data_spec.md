# Level 1 data specification

Processed items require `level1_order,id_item,length_mm,width_mm,height_mm,weight_kg,nesting_height_mm,stackability_code,forced_orientation,max_stackability,used_in_level1`. Only identity, dimensions, weight, order, and inclusion flag affect Level 1.

Containers require `container_id,length_mm,width_mm,height_mm,max_weight_kg,availability,cost,volume_m3,data_status`. Dimensions/weights must be positive, IDs unique, availability binary, and declared volume must match dimensions within `1e-6 m3`.

Benchmark subsets are generated from immutable raw data by one canonical
preprocessor. `prefix` preserves the original behavior. `stable_random` uses a
seeded SHA-256 rank, so the selected IDs do not depend on hidden notebook state.
`volume_stratified` spans the source volume range; `largest_volume` and
`heaviest` define explicit stress profiles. Every processed manifest records
the strategy, selection seed, exact item IDs, source checksum, selection
checksum, and descriptive item statistics. Non-prefix subsets use distinct
filenames and never overwrite the legacy `items_<count>.csv` artifact.
