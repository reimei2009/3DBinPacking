# Level 8 cross-level comparison input

`dataset_small_delivery_items_v1.csv` is a versioned Level 8 input derived
from `data/raw/dataset_small_items_original.csv`. The source file is never
modified: all 501 rows, their order, IDs, physical dimensions, weights, and
advanced 3DBPPsi fields are preserved. Only declared delivery fields are
added, cycling deterministically over five stops.

`container_catalog_c1_c10_v1.csv` reproduces Level 1 containers C1-C5 and
uses the existing deterministic extension rule for C6-C10. Costs are
experimental comparison scores, not freight prices.

Regenerate and verify the tracked files with:

```powershell
.\.venv\Scripts\python.exe .\scripts\prepare_level8_cross_level_data.py
```

The accompanying JSON manifest records source/output checksums and the exact
transformation rule. These inputs support controlled comparisons; they are
not carrier or certified material data.
