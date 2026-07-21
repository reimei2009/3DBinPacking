# Visualization and web architecture

The research UI is an adapter, not an optimization implementation. CLI, notebooks, Streamlit, and a future HTTP API all call the same registry-driven application boundary.

```text
Presentation adapter (Streamlit now; FastAPI/React later)
    -> application/service.py
    -> level and algorithm registries
    -> level pipeline
    -> solver or heuristic
    -> independent validator
    -> versioned run artifacts
    -> visualization/scene.json
    -> Plotly renderer or another frontend
```

## Stable boundaries

- `ExperimentRequest` is the input contract.
- `LevelContract` describes the problem, notation, LaTeX objective, variables, active constraints, inactive features, assumptions, limitations, translations, and source-code mappings.
- `visualization/scene.json` is the backend-neutral geometry contract.
- `manifest.json` identifies the level, algorithm, inputs, source version, and validation status.
- `application/service.py` validates interactive requests and exposes isolated run history.

No Streamlit object is passed into algorithms, pipelines, validators, reporting, or scene generation. Replacing Streamlit with FastAPI and React therefore changes the presentation adapter, not the optimization core.

Vietnamese and English text lives in structured contracts or the small UI translation catalog. Mathematical LaTeX is language-neutral. The UI never maintains a second copy of the formulas.

## Level 1 visualization semantics

The renderer shows fixed-orientation item cuboids and container boundaries. It visualizes only a solution that has passed the independent Level 1 validator. It does not simulate gravity, support, stacking, stability, loading order, or unloading order.

Combined scenes offset containers along the X axis for visual comparison. Item coordinates stored in `scene.json` remain local to their assigned container; the display offset is never written back to the solution.

Opacity presets, item selection, highlighting, and hidden-item lists are transient presentation state. The Plotly adapter accepts them as rendering parameters. They are deliberately excluded from canonical solution and scene data so future Streamlit, FastAPI/React, notebook, or desktop frontends can implement their own controls over the same scene.
