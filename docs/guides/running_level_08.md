# Running Level 8

Level 8 is CLI-only. Best Fit is the experimental primary solver;
FFD is the first-fit comparator. Both require declared delivery metadata.

Generate the manual acceptance input once:

```powershell
.\.venv\Scripts\python.exe .\scripts\generate_level8_synthetic_data.py `
  --profile config\level_08\synthetic\scale_300_c25.yaml
```

Run the 20–300 acceptance suite manually with output previews disabled:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_benchmark.py `
  --suite config\level_08\benchmarks\acceptance_manual.yaml
```

Generate-only scale checks, not solver gates:

```powershell
.\.venv\Scripts\python.exe .\scripts\generate_level8_synthetic_data.py `
  --profile config\level_08\synthetic\scale_500_c50.yaml

.\.venv\Scripts\python.exe .\scripts\generate_level8_synthetic_data.py `
  --profile config\level_08\synthetic\scale_1000_c80.yaml

.\.venv\Scripts\python.exe .\scripts\generate_level8_synthetic_data.py `
  --profile config\level_08\synthetic\scale_5000_c200.yaml
```

The static straight-path model is not a physical unloading simulation. An
invalid result has no comparable objective value and must not be treated as a
valid transport plan.

To measure solver behavior after generation, run Best Fit with one profile at
a time and retain the run directory for diagnosis:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_experiment.py `
  --level level_08 --algorithm extreme_point_best_fit_delivery `
  --config config\level_08\experiments\synthetic_delivery_500_local.yaml `
  --items-count 500 --containers-count 50 --environment local `
  --non-interactive --preview-limit 0
```
