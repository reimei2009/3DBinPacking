# Level 6 runtime-candidate contract

Status: **experimental registered runtime; not a practical default**.

Two fixed-XYZ compound-root constructors are registered:

- `extreme_point_ffd_nesting_fixture` — experimental default;
- `extreme_point_best_fit_nesting_fixture` — experimental comparator.

Both use `explicit_nesting_best_fit_chain_v1`, the Level 6 compound feasibility
policy, and the independent `compound_root_effective_envelope_geometry_v1`
validator. A valid run writes only below `outputs/level_06/runs/<run_id>` and
includes nesting relation/height/compound/support, stack and load CSVs plus the
four validation JSON documents and adapter/policy provenance.

Acceptance covers one-chain and multi-compound synthetic fixtures, including
deterministic repeats. The company-schema fixture additionally proves that a
YAML column mapping flows through preprocessing into the same runtime and
output contract. None of these fixtures establishes large-instance performance,
production data compatibility, or practical-default solver status.
