# Deploy Streamlit demo on Render

This deployment is a public **R&D demo** of the existing Streamlit UI. It
uses the same package, configuration, independent validation, and scene
renderer as local execution. It does not add a second solver or a web-only
packing implementation.

## What is persisted

The service can generate files under `data/processed/` and `outputs/` while it
is running. Render's default filesystem is ephemeral: those files can vanish
when the instance restarts, redeploys, or is replaced. Therefore:

- use the hosted UI for demonstrations and small experiments;
- download any run directory you need before a redeploy;
- keep reproducible research runs on local storage or a future artifact store;
- do not treat the Render demo as a benchmark or checkpoint store.

The Docker image intentionally includes the tracked raw CSV inputs only.
Processed data and run outputs are regenerated automatically by the normal
pipeline and are never committed to Git.

## Local Docker smoke check

From the repository root:

```powershell
docker build -t 3d-container-packing-demo .
docker run --rm -p 8501:8501 -e PORT=8501 3d-container-packing-demo
```

Open `http://localhost:8501`, run a small FFD case, then stop the container
with `Ctrl+C`. Do not run long MILP or large benchmark workloads in the demo.

## Deploy from GitHub using the Blueprint

1. Commit and push `Dockerfile`, `.dockerignore`, `render.yaml`, and this
   guide to the branch you want Render to deploy.
2. Sign in to Render and connect the GitHub account that can access the
   repository.
3. Choose **New → Blueprint**, select the repository, and let Render read
   `render.yaml` from the repository root.
4. Confirm the service name, branch, and the `Singapore` region (or choose a
   nearer supported region if you prefer).
5. Create the Blueprint and watch the first build logs. Render builds the
   root `Dockerfile`; no Build Command or Docker Command override is needed.
6. When the deploy is live, open the generated `*.onrender.com` URL.
7. In the sidebar, select a small level/algorithm/input combination first
   (for example Level 3, Extreme Point FFD, 10 items, 3 containers), run it,
   and confirm both `FEASIBLE` and `VALID`.

Render provides the `PORT` variable for web services. The container binds
Streamlit to `0.0.0.0:$PORT`; do not replace the Docker command with one that
hard-codes localhost or port 8501.

The image also sets `CONTAINER_PACKING_PROJECT_ROOT=/app`. This lets an
installed Python package resolve the repository's tracked `config/` and
`data/` assets instead of incorrectly searching from `site-packages`.

## Redeploy and rollback

With `autoDeploy: true`, a push to the selected branch triggers a new build.
Use Render's deploy history to inspect logs or roll back the service version.
Before deploying a change, save any output you need because generated runs are
not durable on the default filesystem.

## Practical limits

- This is CPU-only. FFD is the safe practical default; Level 3 MILP is limited
  in code to five items and should remain a small exact reference.
- The chosen instance plan must have enough memory for SciPy, Pandas, Plotly,
  and Streamlit. If startup is killed for memory, use a larger Render plan;
  do not weaken solver validation to make the demo start.
- A public demo has no authentication. Do not expose private datasets or
  secrets through it. Add an authentication layer before using it with
  non-public data.
