# Large synthetic physical instances

The shared synthetic generator expands the immutable public item source into
physical instances while preserving empirical correlations between dimensions,
weight, orientation, stackability and nesting fields. Exact attribute groups
become stable item templates; sampling uses their observed source frequencies.

Containers are physical copies of declared types. Instances with the same
`container_type_id` have identical dimensions, payload and experimental cost;
only their physical `container_id` differs. This models a fleet containing many
units of the same equipment type.

Level 8 delivery priority and stop metadata are written as a separate enrichment
and joined into `solver_items.csv`. Future levels may add their own explicit
enrichment without changing the physical population. No Level 9 or Level 10
semantics are inferred by this generator.

Generated files are reproducible but intentionally untracked under
`data/interim/synthetic/<profile_id>/`. The manifest records source and output
checksums, seed, template/type distributions and aggregate volume/payload
capacity evidence.

Generate the local R&D profile:

```powershell
.\.venv\Scripts\python.exe .\scripts\generate_synthetic_instances.py `
  --profile config\synthetic\scale_1k_100.yaml
```

The `scale_10k_500` and `scale_100k_5k` profiles are intended for manual
data-pipeline testing. They are not solver acceptance benchmarks. The current
validated R&D ceiling is 100k items; `stress_1m_50k` and all other 1m profiles
are retained only as deferred, unvalidated references and must not be treated
as execution, CI or acceptance evidence. Tests may parse their YAML contracts
but must not generate the populations.

Profiles declare one of two usage classes. `solver_research` requires both the
realized volume and payload margins to meet the declared threshold (1.40 by
default). `data_pipeline_only` proves only aggregate capacity and always records
`solver_acceptance_allowed: false`, even if its sampled population happens to
have a generous margin. Aggregate capacity never proves geometric packability.

Capacity-safe research profiles use fleets dominated by identical C5 physical
instances: `scale_10k_700`, `scale_100k_7k`, and `scale_1m_70k`. The 100k/7k
and 1m/70k profiles remain declarative data-generation exercises until the
solver has an explicit scale gate; neither is solver acceptance evidence.

## Dataset usage guard

Experiment configs that reference `data/interim/synthetic/` must explicitly
declare their `generation_manifest` and expected usage class. Preparation and
load-performance workflows accept both profile families after checking paths
and checksums. Solver experiments and benchmark acceptance reject
`data_pipeline_only` profiles before invoking an algorithm or creating a
benchmark output directory. There is intentionally no force override.

```yaml
dataset_policy:
  generation_manifest: data/interim/synthetic/<profile>/generation_manifest.json
  expected_usage_class: solver_research
```

Use `empirical_scale_10k_500_pipeline_only.yaml` only with the `prepare`
command. Use a solver-qualified profile for an experiment; aggregate capacity
alone is not sufficient evidence of geometric packability.

## Inspect generated datasets without a solver

`inspect_generated_dataset.py` validates the generation manifest, every
declared file checksum, cross-file physical identities, schema, row counts and
aggregate capacity evidence. It never calls preprocessing or a packing solver,
and never prints the item-ID population.

Streaming mode is the default for 10k--100k pipeline profiles:

```powershell
.\.venv\Scripts\python.exe .\scripts\inspect_generated_dataset.py `
  --manifest data\interim\synthetic\empirical_scale_10k_500_v1\generation_manifest.json `
  --mode stream
```

Use `both` on a bounded profile to compare the bounded-memory reader with the
normal pandas/source-adapter materialization path:

```powershell
.\.venv\Scripts\python.exe .\scripts\inspect_generated_dataset.py `
  --manifest data\interim\synthetic\empirical_scale_1k_100_v1\generation_manifest.json `
  --mode both
```

Each invocation creates a unique level-isolated run directory and records
runtime, rows/second, MB/second, process RSS and `tracemalloc` heap peaks for
each phase. A stream failure prevents materialization in `both` mode. The run
manifest explicitly records `solver_invoked: false` and `objective_value:
null`; inspection is data-pipeline evidence, never solver acceptance evidence.

The versioned inspection baseline is recorded in
`docs/reports/manual/generated_dataset_scale_baseline_20260803.md`. Profile
configuration availability must not be confused with validation: one-million
item profiles were deliberately not executed in the current R&D phase.
