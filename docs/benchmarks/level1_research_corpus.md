# Level 1 research corpus

The canonical local corpus is `config/level_01/benchmarks/research_corpus.yaml`.

| Case | Group | Purpose | Reference |
|---|---|---|---|
| `small_easy_i5_c2` | small | fast regression and exact quality gap | MILP |
| `small_tight_i10_c2` | small | payload-tight feasible packing | MILP |
| `small_infeasible_i10_c1` | small | aggregate payload infeasibility | MILP proof |
| `medium_mixed_i50_c8` | medium | compare all local heuristics | best known |
| `large_scalability_i100_c15` | large | constructive CPU scalability | best known |

Run it with:

```powershell
python scripts\run_benchmark_corpus.py --corpus config/level_01/benchmarks/research_corpus.yaml
```

Every case uses the first declared number of rows from the immutable public source CSV and the deterministic Level 1 container definitions. The corpus does not claim statistical coverage of all 3D packing distributions. Its immediate role is reproducible regression, exact-gap measurement on small instances, failure-semantics testing, and local scalability tracking. Additional public benchmark families should later be added as separately versioned corpora with source provenance, rather than silently changing this corpus.

Read `references.csv` before comparing gaps. `proven_optimal` and `proven_infeasible` come only from exact MILP outcomes. `best_known` means the best validated solution observed in that corpus execution and may improve in a future run.
