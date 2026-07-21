# Running the Streamlit 3D research app

## Windows

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
python scripts\run_web_app.py
```

Open the local URL printed by Streamlit, normally `http://localhost:8501`.

The default language is Vietnamese. Use **Ngôn ngữ / Language** in the sidebar to switch to English. The **Mô hình toán học** tab renders the active level's notation, variables, objective, and constraints with LaTeX and shows the canonical source-code mapping for each expression.

## Linux

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
python scripts/run_web_app.py
```

## Workflow

1. Select an implemented level. Only `level_01` is currently available.
2. Select a compatible algorithm.
3. Enter item count, container count, seed, environment metadata, and algorithm-specific settings.
4. Click **Run experiment**.
5. Review solver status and independent validation status.
6. Inspect the combined scene or one used container.
7. Open previous immutable runs from **Run history**.

Every execution uses the same pipeline as the CLI and writes to a new directory under `outputs/<level>/runs/<run_id>/`. The UI never overwrites an earlier run.

## Important Level 1 limitation

The 3D view is a geometric and payload visualization. It is not evidence of physical stability because Level 1 does not model gravity, support, stacking, fragility, center of gravity, or load/unload order.
