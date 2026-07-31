# ADR-0027 — Optional routing enrichment after Level 8 validation

## Status

Accepted.

## Decision

Level 8 routing is an optional post-processing enrichment. The declared
`delivery_priority` order remains unchanged. Routing cannot alter container
selection, placement coordinates, solver objective, static LIFO validation, or
sequential replay.

The canonical provider interface has two implementations:

- `DeclaredOrderOfflineProvider`, a deterministic Haversine fallback;
- `GoogleRoutesProvider`, a server-side Compute Routes adapter.

The Google web-service key is read only from `GOOGLE_ROUTES_API_KEY`. It is
never written to resolved configuration, logs, request snapshots, manifests,
or route artifacts. A separately restricted `GOOGLE_MAPS_BROWSER_KEY` may be
used by the browser renderer. Missing key, quota exhaustion, timeout, or API
failure falls back to the offline provider when explicitly configured.

Every successful enrichment snapshots its stops and sanitized provider
evidence under the immutable run's `routing/` directory. Independent
`validate_run` checks schemas, declared stop order, leg totals, checksums, and
secret non-persistence without contacting Google again.

## Consequences

- Results remain reproducible without Internet access.
- Route distance and duration are display metrics, not optimization metrics.
- No waypoint optimization, VRP, GPS tracking, or transport-device simulation
  is implied.
