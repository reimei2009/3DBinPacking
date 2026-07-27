# Level 6 declared-nesting fixture

`declared_nesting_fixture_items.csv` is a tracked synthetic research fixture,
not a public 3DBPPsi record and not company production data. It contains one
explicit compatible `HOST-001 -> CHILD-001` relation for acceptance testing of
the Level 6 compound-root runtime.

`declared_nesting_chain_fixture_items.csv` is a second tracked synthetic
fixture with the explicit chain `ROOT-001 -> MIDDLE-001 -> CHILD-001`. It
checks depth-two construction and the effective-height equation
`120 + 25 + 20 = 165 mm`; it is likewise not a performance benchmark.

`declared_nesting_multi_compound_fixture_items.csv` adds independent
`TOP-001`. Its container floor is exactly occupied by the chain root, forcing
the top compound to use the root's external top face. It tests compound support,
stackability and load transfer without representing production data.

`company_schema_nesting_fixture_items.csv` uses deliberately different,
company-style column names and is normalized only through its YAML mapping.
It is synthetic: it proves source adapter → preprocessing → Level 6 runtime
integration but does not represent, expose, or validate any real company data.

Its schema is normalized by
`config/common/data_sources/level_06_declared_nesting_fixture.yaml`. The raw
fixture remains immutable; generated normalized files belong under
`data/processed/level_06/` and experiment evidence under `outputs/level_06/`.
