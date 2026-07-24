# Level 6 runtime semantics design

Status: **designed, not active**. This document defines the contract a future
Level 6 feasibility policy must implement; it does not activate a solver.

## Canonical representation

The solver stores every item and explicit `host -> child` nesting relation.
For external geometry, a complete nesting chain is projected as one compound:

- the root keeps its global container position and horizontal footprint;
- each child is a logical member, not an independently overlapping global box;
- the compound effective height is the root outer height plus every declared
  child increment along the chain;
- the compound external weight is the sum of all member weights.

This avoids silently treating a raw child/host overlap as valid under the old
pairwise non-overlap validator.

## Constraint composition

| Inherited family | Level 6 composition |
| --- | --- |
| Boundary and non-overlap | Evaluate projected root compounds only. |
| Payload | Sum every original item weight, equivalently compound weights. |
| Support and stackability | Only the compound root may expose external support faces or a stack relation. |
| Load transfer | Transfer the compound total weight through root external contacts. |
| Internal forces | Inactive: no pressure, internal load path, deformation, or stability claim. |

The pure projection in `src/container_packing/levels/nesting_runtime.py` is a
planning primitive. It intentionally does not modify `Placement`, infer child
coordinates, or call an existing solver/validator.

`src/container_packing/levels/level_06_compound_validation.py` independently
checks compound boundary, pairwise non-overlap, exact union support ratio, and
base-center support on fixtures. It remains separate from the Level 5 runtime
because raw child boxes are not yet represented by a nesting-aware solver.

The fixture-only Level 6 bundle consumes this compound evidence for its
stackability and recursive load-transfer checks. It exports compound support,
stack, and load artifacts keyed by root compound ID; this is not a solver
runtime and does not activate Level 6 in the registry.

## Required runtime gate

A later runtime may activate only after it validates both the inherited Level 5
solution and the compound projection. Nested members cannot be separately used
as external supporters, stack parents, or load-transfer nodes. The actual
insertion coordinates and material-contact behavior remain outside this level.

The controlled candidate contract is frozen in
`config/level_06/runtime_candidate.yaml` and exposed only as the experimental
`extreme_point_ffd_nesting_fixture` option. It has no solver portfolio or
large-instance benchmark. See `level6_runtime_candidate_contract.md` for its
required fixture evidence and explicit manual promotion gate.
