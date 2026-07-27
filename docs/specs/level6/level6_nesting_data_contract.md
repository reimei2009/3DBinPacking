# Level 6 data contract — explicit nesting metadata

Status: **experimental compound-root runtime registered**.

Level 6 inherits Level 5 and enables nesting only where the source explicitly
declares compatibility. The 3DBPPsi `nesting_height_mm` field remains preserved
but inactive: it does not by itself prove compatible hosts, depth semantics or
incremental height.

## Canonical optional fields

| Field | Meaning |
| --- | --- |
| `nesting_group_id` | Explicit compatibility group. |
| `nesting_role` | `none`, `host`, `child`, or `both`. |
| `inner_length_mm`, `inner_width_mm`, `inner_height_mm` | Usable internal host dimensions. |
| `max_nesting_depth` | Maximum resulting chain depth for a host. |
| `nesting_increment_height_mm` | Incremental vertical consumption of a nested child. |
| `nesting_data_source` | Provenance; `undeclared` disables nesting safely. |

An active relation requires matching non-empty groups, compatible roles,
declared inner dimensions, a valid resulting depth, and a declared child
increment. Missing optional metadata leaves an item packable as
`nesting_disabled_undeclared`.

## Runtime semantics

Relations are deterministic chains: each item has at most one host and one
child. A root contributes its outer height; each nested child adds its declared
increment:

\[
H_{chain}(i)=H_{chain}(host(i))+\Delta h_i.
\]

The runtime projects every chain to one external compound root. Boundary,
non-overlap, support, stackability and static external load transfer validate
those compounds; raw nested children are logical members. Internal nesting
forces, pressure, and internal load transfer remain inactive.

## Source adapters

`CsvSourceAdapter` maps arbitrary CSV aliases to the canonical fields through
YAML and preserves unused columns in provenance. The tracked
`company_schema_nesting_fixture` is a synthetic end-to-end acceptance source
with non-canonical field names; it does not stand in for real company data.
