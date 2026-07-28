# Level 8 fixture semantic baseline

Status: **PASS — semantic evidence only; not an efficiency benchmark.**

| Fixture | Input SHA-256 | Expected baseline | Expected delivery-aware result |
|---|---|---|---|
| One-stop LIFO | `8ab62521df3c0a561cc8f5abac6fb72b6c3c7b3dc813f26613dc2c538cd51c08` | Validation-only, valid | N/A |
| Two-stop / two-container | `c0b3ba3f4ef1f68b3193d4bd0a2dd973ec22746d415fd19b2fc3901ea8c20ac` | Best Fit baseline is LIFO-invalid | Best Fit is valid, deterministic, zero rehandle |
| Three-stop / two-container | `743e001ff3fe038c5c2cb6a42d1293b103807b8284a8a6b664cb429da21212a8` | Best Fit baseline is LIFO-invalid with direct rehandles | Best Fit and FFD are valid, deterministic, two containers, zero rehandle |

All successful fixture runs must produce the same placement signature for a
fixed input/seed and preserve independent Level 1–8 validation evidence. The
canonical output checksums are verified by `tests/test_level8_cli_runtime.py`;
generated run directories are intentionally not committed.

The fixtures only validate a static, straight-path `x_min` unload model. They
do not model equipment, staging space, a full removal sequence, or transport
certification.
