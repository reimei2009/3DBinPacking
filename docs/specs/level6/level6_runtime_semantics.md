# Level 6 runtime semantics design

Status: **implemented as an experimental fixed-XYZ portfolio**. This document
defines the active compound-root semantics; it does not claim production
readiness.

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

The pure projection in `src/container_packing/levels/nesting_runtime.py` is the
shared planning primitive. `Level06CompoundAdapter` constructs the relation
graph once, projects compound roots, invokes the selected solver, expands
logical members, and then invokes independent validation.

`src/container_packing/levels/level_06_compound_validation.py` independently
checks compound boundary, pairwise non-overlap, exact union support ratio, and
base-center support. The Level 6 bundle consumes this compound evidence for
stackability and recursive load-transfer checks and exports artifacts keyed by
root compound ID.

## Search invariant

FFD, Best Fit, Hill Climbing, and Simulated Annealing search only over compound
roots. Hill and SA use Best Fit for initial construction and repair. Relocate,
swap, reinsert, and container-elimination operations cannot separate a nested
member or mutate a relation. Nested members cannot be separately used as
external supporters, stack parents, or load-transfer nodes.

The controlled portfolio contract is frozen in
`config/level_06/runtime_candidate.yaml`. It is accepted only on deterministic
semantic fixtures and has no large-instance performance claim. Actual insertion
coordinates and material-contact behavior inside a nested chain remain outside
this level.
