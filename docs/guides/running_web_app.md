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

1. Select an implemented level (`level_01` or `level_02`).
2. Select a compatible algorithm.
3. Enter item count, container count, seed, environment metadata, and algorithm-specific settings.
   In Level 2, the **Minimum supported-area ratio α** control overrides
   `support.threshold` for that one run. Its valid range is `0.01` to `1.00`;
   the default is `0.80`. The selected value is written to the run's
   `resolved_config.yaml` and manifest metadata. Base-center support remains
   mandatory under the Level 2 contract.
4. Click **Run experiment**.
5. Review solver status and independent validation status.
6. Inspect the combined scene or one used container.
7. Open previous immutable runs from **Run history**.

## 3D display controls

- The default view opens the first used container rather than the combined scene.
- **Rõ khối / Solid** uses opacity `0.92` and is the default.
- **Cân bằng / Balanced** uses opacity `0.75`.
- **X-Ray** uses opacity `0.30`.
- The opacity slider supports manual values from `0.20` to `1.00`.
- Selecting an item renders it at opacity `1.00`, dims other visible items to `0.20`, adds a dark outline, and shows its position, dimensions, and weight.
- **Ẩn các kiện / Hide items** temporarily removes selected items from the view.

These controls change presentation only. They never modify `scene.json`, placements, validation, metrics, or solver output.

Every execution uses the same pipeline as the CLI and writes to a new directory under `outputs/<level>/runs/<run_id>/`. The UI never overwrites an earlier run.

## Level 8 logistics demo

The UI distinguishes four data profiles:

- Quick logistics fixture: 6 items / 2 containers / 3 stops;
- Logistics semantics fixture: 20 items / 5 small fixture containers / 3 stops;
- Cross-level comparison: 20 public items with the same C1-C5 catalog used by
  Levels 1-7 and five declared delivery stops;
- Synthetic research: custom up to 100 items / 10 containers / 5 stops.

Only compare runs when dataset ID, container catalog ID, selected-item
checksum, selection strategy, and seed all match. The sidebar displays these
identifiers and previews container dimensions, volume, payload, and cost.

Without `GOOGLE_ROUTES_API_KEY`, only deterministic offline routing is shown.
It follows declared delivery priority, calculates Haversine straight-line
distance, and estimates duration at 35 km/h. It does not use a road network,
traffic data, billing account, or external API.

Choose either `prefix` or deterministic `stable_random` item selection. The
research dataset and its generator manifest/checksums are tracked under
`data/raw/level_08/web_demo/`; 300-item cases remain CLI-only.

The default stop CSV can be replaced by an uploaded CSV containing one depot
and at most ten delivery stops. The file is checksummed and copied into the
immutable run. Route order always follows declared delivery priority; the UI
does not optimize waypoints.

When sequential replay is enabled, its persisted event stream supplies the
play/pause, previous/next, slider, speed, current stop, highlighted map marker,
and 3D item visibility. This remains deterministic offline replay, not
equipment, staging-space, GPS, or real-time simulation.

## Same-instance benchmark dashboard

Open **So sánh benchmark**, choose at least two algorithms, then enter one item
count, one container count, one deterministic item-subset policy, shared seeds,
and repetitions. **Chạy benchmark so
sánh** executes every selected algorithm against exactly that instance and
selects the new immutable benchmark run automatically.

Read the dashboard in this order:

1. valid-solution rate;
2. mean containers used (Level 1 primary objective);
3. container cost for equal container counts (secondary objective);
4. runtime and runtime-versus-quality trade-off;
5. Big-M objective only as diagnostic detail.

The runtime axis uses a logarithmic scale because exact, constructive, and
metaheuristic methods can differ by several orders of magnitude.

## Important Level 1 limitation

The 3D view is a geometric and payload visualization. It is not evidence of physical stability because Level 1 does not model gravity, support, stacking, fragility, center of gravity, or load/unload order.
