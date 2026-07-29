# ADR-0026: Make sequential replay an opt-in Level 8 hard gate

Status: Accepted.

## Context

The static Level 8 LIFO validator proves only that the final placement has no
declared later-priority straight-path blocker. It does not prove that every
remaining packing state stays valid while items are removed.

## Decision

Generic Level 8 Best Fit and FFD runs may enable deterministic sequential
replay through config. Replay remains disabled by default.

When enabled:

- packing and static Level 1--8 validation must pass before planning starts;
- unload order is delivery priority, container ID, then dependency order;
- load order reverses delivery priority while preserving supporter/host before
  dependent precedence;
- each stop opens and closes every involved container separately;
- Level 1--7 evidence is recomputed from the remaining state after every
  removal;
- replay failure is a hard final validation failure and suppresses objective
  reporting;
- seven artifacts are written under the isolated run's `simulation/`
  directory and `validate_run` rebuilds them independently.

The Streamlit view is a read-only consumer of persisted events. It never plans
or validates a sequence.

## Consequences

This provides deterministic acceptance evidence for multiple containers and
stops without changing Best Fit/FFD construction. It adds runtime only when
explicitly requested. The model still excludes SimPy, equipment motion,
staging space, route optimization, wall-clock telemetry, and physical
certification.
