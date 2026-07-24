# Level 4 data contract — stackability

## Scope

This contract activates `stackability_code` and `max_stackability` without
activating load-bearing. It is designed so a larger operational dataset can
replace the current research CSV by changing field mapping and compatibility
configuration rather than rewriting the packing core.

## Raw-to-canonical mapping

| Raw field | Canonical field | Status | Validation |
| --- | --- | --- | --- |
| `stackability_code` | `stack_group_id` | used | non-empty after trimming; compare as string, never numeric ordering |
| `max_stackability` | `max_stack_layers` | used | positive integer |
| `id_item` | `item_id` | used | unique |
| dimensions/orientation | geometric base | inherited | validated by Level 3 |
| weight | payload | inherited | validated by Level 3; not used for load-bearing yet |

`stack_group_id` does not mean product type, hazard class, or load capacity.
It only expresses compatibility under the configured `same_stackability_code`
rule.

## Compatibility and non-stackable cases

The canonical default is equality:

```text
compatible(i, j) = (stack_group_id(i) == stack_group_id(j))
```

No numeric code is intrinsically special. A future dataset can mark exceptions
via `non_stackable_codes`, `non_stackable_item_ids`, or a versioned
compatibility-matrix file. Those are explicit inputs captured in the resolved
configuration and run manifest.

## Stack graph output contract

Each placement exposes:

| Field | Meaning |
| --- | --- |
| `direct_parent_item_id` | declared direct stack parent, empty for floor root |
| `stack_id` | deterministic root-derived stack identifier |
| `stack_depth` | zero for root, one for direct child, etc. |
| `stack_layer_count` | total layers in the item's root-to-leaf stack |
| `max_stack_layers_effective` | minimum configured cap along its parent chain |

The fields are exported in `solution/stacks.csv`, the canonical solution
payload, validation documents, reports, and scene item metadata.

## Provenance and upgrade rule

The source README confirms same-code stackability. It does not document the
precise semantics of `max_stackability`; this repository's interpretation is
therefore declared in `stackability_rules.yaml` with
`source_status: project_v1_convention_pending_field_definition`.

For a production dataset, add a new mapping/config version and preserve the
original source values. Never overwrite a historical processed CSV or change a
previous run's interpretation in place.
