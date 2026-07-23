# Level 3 orientation data contract

Status: planned contract; no Level 3 processor or solver consumes it yet.

## Source fields

| Field | Level 3 status | Rule |
| --- | --- | --- |
| `length_mm`, `width_mm`, `height_mm` | used | Original dimensions in mm. |
| `forced_orientation` | preserved, inactive | Raw values are not mapped until source semantics are verified. |
| `weight_kg` | used | Unchanged by orientation. |
| `stackability_code`, `max_stackability`, `nesting_height_mm` | preserved, inactive | Reserved for later contracts. |

The upstream repository describes its item rotation as rotation on the
horizontal plane while keeping the z-axis unchanged. It also describes
stackability as a separate same-code property. The Level 3 contract therefore
activates horizontal orientation only and does not activate stackability.

Source: [MRVSmartNetworks container-loading heuristics README](https://github.com/MRVSmartNetworks/container_loading_heuristics).

## Derived fields

The Level 3 preprocessor will add, without modifying raw data:

| Field | Type | Meaning |
| --- | --- | --- |
| `orientation_profile_id` | string | Declared source of allowed orientations. |
| `allowed_orientation_codes` | JSON array | Deduplicated subset of `XYZ`, `YXZ`. |
| `orientation_data_status` | string | `synthetic_orientation_profile` or future verified mapping ID. |

`allowed_orientation_codes` is canonical input for all algorithms and the
validator. Solvers must not inspect `forced_orientation` directly.

## Validation

- dimensions and weight remain positive;
- every item has at least one allowed code;
- codes are unique and belong to `{XYZ, YXZ}`;
- `YXZ` is removed when it gives the same dimensions as `XYZ`;
- a selected code must be included in that item's allowed set;
- output dimensions must exactly match the selected code.
