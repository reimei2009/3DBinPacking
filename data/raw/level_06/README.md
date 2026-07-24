# Level 6 declared-nesting fixture

`declared_nesting_fixture_items.csv` is a tracked synthetic research fixture,
not a public 3DBPPsi record and not company production data. It contains one
explicit compatible `HOST-001 -> CHILD-001` relation for acceptance testing of
the Level 6 compound-root runtime.

`declared_nesting_chain_fixture_items.csv` is a second tracked synthetic
fixture with the explicit chain `ROOT-001 -> MIDDLE-001 -> CHILD-001`. It
checks depth-two construction and the effective-height equation
`120 + 25 + 20 = 165 mm`; it is likewise not a performance benchmark.

Its schema is normalized by
`config/common/data_sources/level_06_declared_nesting_fixture.yaml`. The raw
fixture remains immutable; generated normalized files belong under
`data/processed/level_06/` and experiment evidence under `outputs/level_06/`.
