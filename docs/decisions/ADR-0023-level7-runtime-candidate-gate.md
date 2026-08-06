# ADR-0023: Promote Level 7 only as a validation-only CLI fixture

## Status

Superseded.

Thay thế bởi `docs/levels/level_07.md`. Fixture validation-only vẫn được giữ
cho regression và acceptance evidence, nhưng không còn là algorithm Level 7
duy nhất.

## Decision

Register `level_07_fixture_validation_bundle` as the sole Level 7 algorithm.
It is a CLI-only validation fixture, not a packing solver. The frozen contract
accepts only the declared prefix 4-item / 1-container / local / XYZ fixture.
It requires inherited independent Level 6 compound evidence, independent
COG/balance evidence, and isolated Level 7 artifacts.

## Consequences

The level registry and CLI expose the fixture for `list`, `prepare`, `run`, and
`validate`; Streamlit filters it out via `web_visible=False`. The runtime returns
`VALIDATION_ONLY` and never an objective. Best Fit and FFD cannot consume
balance constraints until a separate promotion decision.
