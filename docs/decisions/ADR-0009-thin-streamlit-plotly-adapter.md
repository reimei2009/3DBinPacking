# ADR-0009: Use a thin Streamlit and Plotly research adapter

## Decision

Use Streamlit for the current local R&D interface and Plotly for interactive 3D rendering. Keep both behind an application boundary and a versioned backend-neutral `scene.json` contract.

## Rationale

Streamlit minimizes UI development effort while algorithms and level contracts are still changing. Plotly supports interactive cuboids, hover metadata, camera controls, and future browser reuse through Plotly.js. The optimization core must not import Streamlit.

## Consequences

- A future commercial frontend may replace Streamlit without rewriting solvers, validators, orchestration, level metadata, or scene generation.
- Authentication, database persistence, job queues, multi-user isolation, and production deployment are intentionally not part of this R&D adapter.
- Generated HTML and Streamlit views consume canonical run artifacts; they are derived outputs, not solver inputs.
