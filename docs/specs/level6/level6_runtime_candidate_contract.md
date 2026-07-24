# Level 6 runtime-candidate contract

Status: **experimental registered candidate; not a practical default**.

The candidate algorithm ID is `extreme_point_ffd_nesting_fixture`. It uses
fixed `XYZ` dimensions, `explicit_nesting_best_fit_chain_v1`, and the compound
Level 6 feasibility policy. Its final authority is the independent
`compound_root_effective_envelope_geometry_v1` validator.

The candidate may write only to `outputs/level_06/runs/<run_id>`. A valid run
must include nesting relation/height/compound/support, stack and load CSVs;
the four corresponding validation JSON documents; and provenance for the
adapter, relation construction, feasibility policy and compound validation.

A controlled registry promotion exposes only this candidate through
`config/level_06/experimental.yaml`; it does not add a benchmark suite or make
the solver the default for any other level. Acceptance fixture
`declared_chain_host_child_v1` is run twice. Both runs must
be `FEASIBLE`, independently `VALID`, have one compound and one relation, and
share the same solution signature. This does not authorize registry, CLI or UI
additional solver portfolio work. It does not establish performance on public
or company-scale data.
