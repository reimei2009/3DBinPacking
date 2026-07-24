# Level 6 data contract — explicit nesting metadata

Status: **contract and pure independent-validator checkpoint; no Level 6 runtime is registered**.

Level 6 will inherit Level 5 and may reduce vertical consumption only for an
explicitly declared nesting relation. The existing 3DBPPsi `nesting_height_mm`
field remains preserved/inactive because its compatibility and increment
semantics are not verified.

## Canonical optional fields

| Field | Meaning |
| --- | --- |
| `nesting_group_id` | Explicit compatibility group. |
| `nesting_role` | `none`, `host`, `child`, or `both`. |
| `inner_length_mm`, `inner_width_mm`, `inner_height_mm` | Usable internal host dimensions. |
| `max_nesting_depth` | Maximum resulting chain depth for a host. |
| `nesting_increment_height_mm` | Declared incremental vertical consumption for a nested child. |
| `nesting_data_source` | Provenance; `undeclared` disables nesting safely. |

An active relation requires equal non-empty groups, compatible roles, declared
inner dimensions containing the child in its selected orientation, a valid
resulting depth, and a declared child increment. Missing optional metadata does
not reject an item; it produces `nesting_disabled_undeclared`.

The current checkpoint does not change placement dimensions, support,
load-bearing transfer, objective, solver, UI, or level registry. The pure
validator only recomputes explicit nesting chains and effective height; it does
not relax inherited non-overlap checks or declare an overlapping placement
geometrically valid.

## Pure chain-height semantics

Each direct relation is `host -> child`. A host and child must be in the same
container; each item has at most one host and one child, so relations form a
chain rather than an ambiguous tree. Depth starts at zero for the root. The
root contributes its outer placement height and every nested child contributes
its declared `nesting_increment_height_mm`:

\[
H_{chain}(i)=H_{chain}(host(i))+\Delta h_i.
\]

The engine computes depth itself and never trusts an input depth. It checks the
host's declared cap, compatibility, selected child dimensions, and clearance.
The planned runtime output schema is `nesting_relations.csv`,
`nesting_height.csv`, and `nesting_validation.json`.

For the current fixture-only composition API, these artifacts are emitted by
the shared run writer together with the inherited Level 5 artifacts. The
caller supplies relations explicitly; the API does not infer them from geometry
and `nesting_runtime_enabled` remains false.
