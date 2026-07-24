# ADR-0020: Gate Level 6 runtime promotion through a fixture contract

## Status

Accepted.

## Decision

Freeze `extreme_point_ffd_nesting_fixture` as the only Level 6 runtime
candidate. It is registered only as an experimental solver. Its contract
requires deterministic declared relation construction, compound-root FFD,
compound candidate feasibility, independent compound validation and isolated
artifacts.

## Promotion gate

Before adding any other Level 6 solver, the `declared_chain_host_child_v1`
fixture must return `FEASIBLE` and `VALID` twice with the same signature,
produce every declared artifact, and leave Levels 1--5 regression-clean. A
human review is mandatory before further promotion. No large benchmark is part
of this gate.
