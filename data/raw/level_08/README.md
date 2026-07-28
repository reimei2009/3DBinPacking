# Level 8 synthetic delivery inputs

`unloading_semantic_fixture_items.csv` is tracked semantic test data. It uses
explicit delivery priority and stop metadata through
`config/common/data_sources/level_08_synthetic_delivery.yaml`.

The `generated/` directory is intentionally untracked. Generate reproducible
large profiles with `scripts/generate_level8_synthetic_data.py`; every run
writes item CSV, container CSV and a provenance manifest with the selected
profile, seed and checksums. These profiles are research inputs, not customer
or carrier data.
