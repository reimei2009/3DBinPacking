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

## Scale gate inventory-aware Level 1

Hai profile fleet phục vụ nghiệm thu inventory-aware search là `fleet_500_t10`
và `fleet_5000_t25`: lần lượt 500/10 và 5.000/25 physical-container/type.
Profile 5.000 dùng variant tái lập từ type nguồn; manifest ghi policy sinh
variant và checksum. Raw catalog không bị sửa.

Sau khi generate profile, chạy Gate A không gọi solver:

```powershell
.\.venv\Scripts\python.exe .\scripts\inspect_generated_dataset.py `
  --manifest data\interim\synthetic\level_01_inventory_fleet_5000_t25_v1\generation_manifest.json `
  --level level_01 `
  --intent inventory_scale_gate `
  --mode stream
```

Report gồm số physical container, số equivalent type, lower bound, preview lazy
candidate và peak memory. Gate B chạy riêng qua experiment config sau khi profile
đã được generate; không commit CSV sinh ra.

Capacity-safe research profiles use fleets dominated by identical C5 physical
instances: `scale_10k_700`, `scale_100k_7k`, and `scale_1m_70k`. The 100k/7k
and 1m/70k profiles remain declarative data-generation exercises until the
solver has an explicit scale gate; neither is solver acceptance evidence.

## Dùng fleet trong Streamlit

Level 1 có registry UI riêng cho `fleet_500_t10` và `fleet_5000_t25`. Các
catalog này vẫn chỉ là CSV generated trong `data/interim/synthetic/`, vì vậy
không được commit. Hãy generate profile trước khi chọn nó trên web. Nếu file
hoặc manifest thiếu, UI sẽ báo trạng thái chưa sẵn sàng và in đúng command
generate; nó không thay catalog đó bằng C1--C5.

UI chỉ hiển thị bảng gộp theo container type. Số `physical container` là quy
mô kho, còn `maximum used-container count` là budget để solver chọn tối đa bao
nhiêu container từ toàn catalog. Đây là hai số khác nhau.

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
## View solver-research Level 2 tối đa 20.000/5.000

Corpus `empirical_scale_100k_5k_v1` tiếp tục là `data_pipeline_only`. Công cụ
`scripts/materialize_level2_solver_research.py` chỉ đọc corpus này và tạo một view
prefix bất biến dưới `data/interim`, tối đa 20.000 item cùng 5.000 container. Công cụ
tính lại schema, ID uniqueness, fixed-orientation compatibility, checksum, volume và
payload margin; chỉ publish manifest `solver_research` khi mọi gate dữ liệu đạt yêu
cầu. Đây là qualification dữ liệu, chưa phải bằng chứng runtime của solver.

Sau benchmark scale thủ công, `scripts/qualify_level2_large_web_profile.py` xác minh
trạng thái, objective leakage, deterministic repeat và peak memory. Chỉ gate artifact
khớp generation-manifest hiện tại mới làm profile xuất hiện trên Streamlit.
