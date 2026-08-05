# Generated dataset inspection baseline — 2026-08-03

## Scope

This report records data-pipeline inspection evidence only. It does not claim
geometric packability, solver feasibility, optimality, or production readiness.
No packing solver was invoked and every inspection manifest records
`objective_value: null`.

The current R&D scale ceiling is 100,000 physical items. One-million-item
profiles remain declarative future references and were not generated or
validated for this checkpoint.

## Results

| Profile | Items / containers | Mode | Status | Stream runtime | Peak RSS | RSS delta | Conclusion |
|---|---:|---|---|---:|---:|---:|---|
| `empirical_scale_1k_100_v1` | 1,000 / 100 | `both` | `VALID` | 0.030 s | 121.0 MB | 0.2 MB | Streaming and source-adapter materialization valid |
| `empirical_scale_10k_500_v1` | 10,000 / 500 | `stream` | `VALID` | 0.280 s | 120.9 MB | 0.1 MB | Pipeline-only profile valid |
| `empirical_scale_100k_5k_v1` | 100,000 / 5,000 | `stream` | `VALID` | 3.043 s | 121.4 MB | 0.19 MB | Maximum validated data-pipeline scale |
| 1m reference profiles | 1,000,000 / 50,000–70,000 | not run | `NOT_VALIDATED` | — | — | — | Deferred beyond the current R&D scope |

The 100k stream processed 105,000 physical rows at approximately 34,510
rows/second and 10.0 MB/second. Its Python heap peak was approximately 0.53 MB.
The generated 100k profile occupied approximately 30.42 MB on disk.

## Evidence runs

- 1k: `20260803T065558565141Z__level_08__dataset_inspection__i1000_c100__seed8100`
- 10k: `20260803T065609277539Z__level_08__dataset_inspection__i10000_c500__seed8500`
- 100k: `20260803T071640017359Z__level_08__dataset_inspection__i100000_c5000__seed85000`

Each run is isolated under `outputs/level_08/runs/<run_id>/` and contains the
inspection request, generation-manifest snapshot, structured log and JSON
report. Generated CSVs remain under `data/interim/synthetic/`. Both locations
are ignored by Git and are not repository artifacts.

## Decision

- Stop scale validation at 100k for the current research phase.
- Permit schema/config parsing only; never generate 1m profiles in tests, CI,
  smoke tests or acceptance runs.
- Retain 1m YAML profiles only as unvalidated future references.
- Return engineering effort to Level 8 packing quality and stop-aware
  fixed-subset construction instead of increasing data volume.
