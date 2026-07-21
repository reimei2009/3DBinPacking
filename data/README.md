# Data policy

- `external/`: immutable third-party source files and provenance notes.
- `raw/`: immutable project inputs kept in Git when their size and license permit.
- `interim/`: generated transformation intermediates; ignored by Git.
- `processed/`: reproducible solver-ready datasets generated from raw data and config; ignored by Git by default.

Generate Level 1 processed data with:

```powershell
.\.venv\Scripts\python.exe scripts\prepare_data.py --level level_01 --config config\level_01\default.yaml
```

Processed data needed as a permanent benchmark fixture must be explicitly documented and force-added in a dedicated change. Experiment outputs belong under `outputs/<level>/runs/<run_id>/` and are not source-controlled.
