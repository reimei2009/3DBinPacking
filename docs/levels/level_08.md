# Level 8 — Delivery order, LIFO, and multiple stops

Trạng thái: **experimental runtime**. Gate sequential replay 100 items đã
`FEASIBLE + VALID`; quan sát 300 items hiện chỉ chứng minh timeout construction
an toàn, có giới hạn thời gian. Evidence canonical nằm tại
`docs/reports/manual/level_08_sequential_scale_baseline.md`.

Streamlit exposes only the config-driven
delivery-aware Best Fit and FFD solvers against a tracked three-stop demo.
Frozen fixtures remain CLI-only regression evidence; neither solver is a
production transport-planning system.

The logistics demo adds four versioned Streamlit profiles: fixture `6/2`,
semantic fixture `20/5`, cross-level comparable `20/5`, and synthetic custom
up to `100/10`. It includes declared stop coordinates, a route provider, a
stop-colored 3D scene, and artifact-driven replay controls.
Routing runs only after a valid packing/replay result and never changes the
objective or any Level 1–8 constraint. The default offline provider is fully
deterministic. Google Compute Routes is optional, server-side, sanitized, and
falls back offline on missing key, timeout, quota, or provider error.

The fixture semantic baseline is recorded in
`docs/reports/manual/level_08_fixture_baseline.md`.

Ba nhóm evidence canonical có mục đích khác nhau:

- `docs/reports/manual/level_08_fixture_baseline.md`: semantics fixture;
- `docs/reports/manual/level_08_sequential_scale_baseline.md`: gate replay và
  bounded runtime;
- `docs/reports/manual/level_08_soft_stop_affinity_gate_20260803.md`: nghiệm
  hợp lệ nhưng chưa đạt target chất lượng container của gate `20/5`.

## Activated semantics

Each item may explicitly declare `delivery_priority`, `delivery_stop_id`, and
`delivery_data_source`. A smaller positive `delivery_priority` is delivered
earlier. Multiple items may share one stop/priority, but one priority cannot
refer to multiple stop IDs.

The initial unloadability model is `straight_path_static_lifo_v1`:

- the configured door is `x_min` by default, with the static exit direction
  `-x`;
- a potential blocker is in the same container, closer to the door, and has a
  positive overlap with the moved item's swept cross-section;
- a blocker with later delivery priority is a LIFO violation and contributes
  one direct rehandle to the static lower-bound count;
- earlier/same-stop blockers remain in the audit trail but are not counted as
  rehandles because they can be removed before the target.

The pure engine supports `x_min`, `x_max`, `y_min`, and `y_max` configuration
values. This does not yet model a physical door opening, lifting, rotation,
staging space, or an executable removal sequence.

## Fixture output contract

A fixture writer can persist independent evidence only under
`outputs/level_08/runs/<run_id>/` and include:

- `solution/unloading_accessibility.csv`;
- `solution/rehandle_plan.csv`;
- `validation/unloading_validation.json`.

These artifacts must record door face, clearance, priority convention, blocker
IDs, direct accessibility, LIFO status, and rehandle count.

`level_08_fixture_validation_bundle` is the validation-only CLI algorithm. It
prepares a versioned fixture input, validates the inherited Level 1--7 bundle,
then independently validates static unload/LIFO evidence. It never reads a
previous run output or invokes a solver.

Run the fixture:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_experiment.py `
  --level level_08 --algorithm level_08_fixture_validation_bundle `
  --items-count 2 --containers-count 1 --environment local `
  --non-interactive --preview-limit 0
```

The run must return `VALIDATION_ONLY` and include all inherited evidence plus
`unloading_accessibility.csv`, `rehandle_plan.csv`, and
`unloading_validation.json` under its isolated Level 8 run directory.

The A/B fixture verifies that a delivery-aware Best Fit tie-break, after
container count, cost, and all inherited hard constraints, can avoid a
later-delivery blocker. The baseline deliberately uses ordinary Best Fit and
is expected to be `INVALID_SOLUTION`; the aware variant must be `FEASIBLE` and
`VALID`:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_experiment.py `
  --level level_08 --algorithm extreme_point_best_fit_delivery_aware_fixture `
  --config config\level_08\experiments\delivery_best_fit_aware_fixture.yaml `
  --items-count 2 --containers-count 1 --environment local `
  --non-interactive --preview-limit 0
```

`delivery_multi_stop_multi_container_*_fixture.yaml` extends this evidence to
four items across two payload-forced containers and two stops (`STOP-A`, then
`STOP-B`). It proves that each container receives independent COG and LIFO
evidence. The baseline remains expected-invalid; the aware variant must be
deterministic and `VALID`. This is still a frozen fixture, not arbitrary input
support.

Before enabling delivery-aware FFD, the CLI-only
`extreme_point_ffd_delivery_negative_control_fixture` proves its fixed
container semantics: `C1` can hold both items but creates a LIFO violation;
`C2` can hold the early item, yet canonical FFD retains the first geometrically
feasible container and correctly reports `INVALID_SOLUTION`. This is expected
evidence, not a solver failure to hide with fallback.

`extreme_point_ffd_delivery_aware_fixture` then uses the same two-container
fixture. It preserves `C1` as the first feasible container, but evaluates its
feasible extreme points (including the declared far-door anchor) and selects a
LIFO-valid placement. Thus it is not global Best Fit or a hidden fallback.

For config-driven local experiments, use `extreme_point_best_fit_delivery`
(primary) or `extreme_point_ffd_delivery` (fast comparator). Both require every
selected row to declare priority, stop, and provenance. Missing or ambiguous
delivery metadata fails before solver execution. The web demo intentionally
uses only the tracked six-item fixture; run the 20–300 item protocol through
the CLI synthetic profiles.

When constructive placement is valid through Level 7 but fails strict LIFO,
the runtime performs bounded local delivery repair on compound roots. It ranks
the largest direct blocker contributors and attempts, in order, in-container
relocation/transfer, leaf swap, and a 4/8/12-root conflict-neighborhood
destroy/reinsert with complete support closures. Each operator has reserved
candidate and time quotas, so relocation cannot consume the swap or
neighborhood budget.
Each accepted intermediate is independently valid through Level 7; only a
final Level 8-valid result is reported as feasible. A monotonic 45-second
deadline (by default) now covers construction and repair together. Construction
checks that deadline between candidates; if it expires, the run returns
`TIME_LIMIT`, writes status evidence only, suppresses the objective, and does
not start repair. Repair receives only the remaining budget, reserves a
separate rescue phase, and may open at most one additional container only after
fixed-container repair. It never rebuilds all selected items.

The delivery-aware construction pass uses reverse loading order: later delivery
priorities are placed first toward the far side, then earlier deliveries are
placed nearer the door. This produces the requested early-stop-near-door final
layout while avoiding the infeasibility caused by trying to occupy door space
with early items before later items have a feasible support-constrained route.
For small instances the runtime can compare this pass with compact construction;
the 300-item profile uses delivery-first directly to preserve its 45-second
pipeline budget.

The final controlled acceptance fixture has three ordered stops (`STOP-A`,
`STOP-B`, `STOP-C`), six items, and two payload-forced containers. The Best
Fit baseline intentionally creates direct later-priority blockers. Delivery-
aware Best Fit and FFD must both remain deterministic, use two containers,
write independent evidence for each container, and finish `VALID`. It does not
enable arbitrary input sizes or change the primary objective.

## Optional deterministic sequential replay

`config/level_08/sequential_simulation_rules.yaml` freezes the future offline
replay vocabulary: deterministic logical timing, strict LIFO with no implicit
rehandling, and artifacts under `simulation/` in the isolated run directory.
`level_08_sequential_validation.py` builds removal precedence from static door
blockers, external support, and explicit nesting relations. It rechecks the
remaining geometry and static LIFO state after each declared removal.
`level_08_sequential_state_validation.py` now provides the fixture-level
callback that rebuilds the complete independent Level 1--7 bundle from the
remaining placements. Explicit nesting relations are filtered to surviving
members; stack parents and load-transfer edges are recomputed, never copied
from a preceding state.

The offline deterministic planner accepts only an initially strict-LIFO-valid
packing and derives topological loading/unloading orders. At every removal it
rebuilds Level 1--7 evidence for the changed container from the raw remaining
snapshot. Unchanged containers retain only their prior certificate: all active
constraints are container-local, while removal is monotonic for bounds,
non-overlap, payload, and supported load. Support/nesting dependencies prevent
removing a supporter or host before its dependent.

- `simulation/simulation_plan.json`;
- `simulation/loading_sequence.csv`;
- `simulation/unloading_sequence.csv`;
- `simulation/events.jsonl`.

It also writes `simulation/stop_summary.csv`,
`simulation/simulation_metrics.json`, and
`simulation/simulation_validation.json`. The latter independently checks event
sequence/timeline and loading/unloading/delivery order; `validate` compares all
seven artifacts against a newly rebuilt plan.

Logical event times are derived solely from the versioned timing profile. Each
stop opens and closes every involved container independently. Unloading keeps
ascending delivery priority as a hard outer order and respects every
support/nesting dependency. Among dependency-ready items at the same stop, the
planner selects the removal whose next container state is closest to the
configured Level 7 COG target. If that locally best branch cannot complete the
current stop, deterministic memoized backtracking tries the next-best branch.
A removal is eligible only when both
longitudinal and lateral COG remain inside the unchanged Level 7 band. If no
complete same-stop order exists, replay stops with the actionable
`NO_BALANCE_SAFE_REMOVAL` diagnostic; it does not widen the band or process a
later stop. Loading still prefers descending priority while reversing
support/nesting dependencies so a supporter or host is always loaded before
its dependent.

`level_08_sequential_replay_fixture` is a CLI-only frozen fixture runtime. It
has one-container and two-container/three-stop acceptance profiles.

Generic Level 8 Best Fit/FFD runs may opt in with:

```yaml
sequential_simulation:
  enabled: true
  required_when_enabled: true
  rules_file: config/level_08/sequential_simulation_rules.yaml
  time_limit_seconds: 45
```

Replay starts only after packing and static Level 1--8 validation pass. When
required, any invalid sequential state makes the run `INVALID_SOLUTION` and
hides its objective. Replay has a separate monotonic 45-second default budget.
On expiry, the run reports `REPLAY_TIME_LIMIT`, stores phase/state diagnostics,
and creates no incomplete simulation plan or event log. `validate` reloads the
input snapshot, rebuilds the graph/order/timeline/metrics, and rejects missing
or altered artifacts. Streamlit only reads persisted events and changes item
visibility/highlighting; it contains no planner or validator logic.

Level 8 construction reuses the canonical Level 7 two-stage balance repair
before static LIFO or sequential replay. A replayed invalid state records its
first failing sequence, item, issue code and issue message in run metadata;
this distinguishes a balance handoff failure from a dependency/LIFO failure.
Generic Level 8 construction also composes strict-LIFO candidate feasibility
with the inherited Level 6 policy. Door-aware candidate generation includes
far-side anchors on supporter top faces, and Level 7 balance repair is only
allowed to retain candidates that remain strict-LIFO valid.

Scale replay profiles additionally enable:

```yaml
sequential_balance_construction_enabled: true
delivery_subset_exhaustive_max_containers: 8
delivery_subset_max_candidates_per_count: 32
```

The delivery-first constructor places priorities in descending order. Every
accepted partial reverse-loading state must already satisfy the Level 7 COG
band, so reversing that construction supplies at least one balance-safe
unloading path. Candidate generation adds target-COG anchors and ranks valid
placements by prospective COG before delivery/geometric tie-breaks.

Container selection uses `adaptive_exact_small_bounded_diverse_large_v1`:

- catalogs up to the configured exact threshold enumerate every subset in
  increasing container-count and cost order;
- larger catalogs retain a bounded portfolio built from cost, volume,
  payload, efficiency and one-swap neighborhoods;
- aggregate payload/volume bounds prune impossible subsets before geometry;
- run metadata records every attempted small-catalog subset and whether its
  constructive packing failed, succeeded or hit the deadline.

This avoids silently missing a middle catalog combination such as `C3+C4`
while preventing combinatorial enumeration on 25--80 container catalogs.
It remains a heuristic feasibility search, not a proof that a failed smaller
subset is mathematically infeasible. The Level 8 policy also rejects a support
edge when its supporter must be delivered earlier than the supported item,
because that relation cannot be replayed in declared delivery order.

Low volume utilization is therefore not sufficient evidence that a container
can be closed: the candidate must also retain exact support, stack/load rules,
static LIFO and a balance-valid state after every removal. The solver summary
exposes the aggregate capacity lower bound and attempted subsets so this gap
is auditable. This stronger construction is opt-in because older semantic
fixtures were designed only for final-state balance, not for balance after
every individual removal.

Quy trình scale được chạy thủ công:

```powershell
.\.venv\Scripts\python.exe .\scripts\generate_level8_synthetic_data.py `
  --profile config\level_08\synthetic\scale_1000_c80.yaml

.\.venv\Scripts\python.exe .\scripts\run_benchmark.py `
  --suite config\level_08\benchmarks\sequential_replay_100_manual.yaml

.\.venv\Scripts\python.exe .\scripts\run_benchmark.py `
  --suite config\level_08\benchmarks\sequential_replay_300_manual.yaml
```

Both suites sample from the same versioned 1000-item source so prefix and
stable-random profiles are genuinely different. The 100-item gate requires
`VALID`. The 300-item observation accepts deterministic `VALID`, explicit
construction `TIME_LIMIT`, or explicit `REPLAY_TIME_LIMIT`. A timeout is not a
successful packing: it has no objective and no partial solution/simulation
artifacts. Kết quả baseline hiện tại phải được đọc từ
`docs/reports/manual/level_08_sequential_scale_baseline.md`, không suy ra từ
một output run đơn lẻ.

## Data and provenance

The cross-level comparison profile uses the versioned inputs under
`data/raw/level_08/cross_level/`. All 501 item rows preserve the public source
order, IDs, dimensions, weights, orientation, nesting, and stackability
fields; only five-stop delivery declarations are added. Its C1-C5 containers
match Levels 1-7 exactly, while C6-C10 follow the same deterministic extension
rule. The preparation script and checksum manifest make this auditable.

Results are comparable only when `dataset_id`, `container_catalog_id`,
`comparison_group_id`, selected-item checksum, selection strategy, and seed
match. Level 8 can still require more containers because delivery/LIFO and
sequential replay add hard constraints.

The tracked 20/5 comparison currently recommends delivery-aware FFD: it finds
four replay-valid containers while Best Fit finds five. The compact Level 7
C3+C4 candidate is retained as a repair target rather than discarded, but its
13 direct rehandles were not eliminated by the bounded Level 8 repair. See
`docs/reports/manual/level_08_cross_level_subset_audit_20260731.md`. This is an
R&D heuristic result, not proof that two or three containers are infeasible.
The 50/8 comparable profile remains outside the web acceptance gate because it
did not yet produce a final Level 8-valid solution.

Kết quả soft stop-affinity chi tiết nằm tại
`docs/reports/manual/level_08_soft_stop_affinity_gate_20260803.md`. Việc giữ
report thất bại quality gate giúp phân biệt rõ `VALID` về constraint với đạt
target tối ưu thực nghiệm; không được dùng report này để tuyên bố infeasible.

Routing defaults to the deterministic offline provider. It follows declared
priority and reports Haversine distance with a 35 km/h duration estimate;
routing remains enrichment and never changes packing or validation.

Legacy 3DBPPsi rows do not have delivery metadata. They are preserved as
`unloading_disabled_undeclared`; no priority is inferred from dimensions,
weight, nesting, stackability, or input order.

`data/raw/level_08/unloading_semantic_fixture_items.csv` is a tracked synthetic
semantic fixture. Configured company CSV aliases are normalized through the
shared source adapter. Reproducible scale profiles create untracked synthetic
inputs for 500–5000 items and 50–200 containers; their YAML profile and seed
are the source of truth.

### Stop-aware fixed-subset construction candidate

Level 8 Best Fit includes an optional hierarchical soft-affinity candidate over
compound roots. The planner evaluates fixed container subsets in increasing
cardinality, processes delivery groups deterministically, and hard-prunes only
individual fit, aggregate payload, and aggregate volume. Its preferred
container is guidance: Best Fit may fall back to another container inside the
same subset when geometry, support, stackability, load bearing, or balance
requires it. Container count and cost are selected by the outer fixed-subset
search; affinity only ranks candidates inside that already selected subset.

`order_id` is the only declaration that groups multiple items as one order. If
it is absent, the item ID is used; items sharing a stop are not silently merged
into one order. Explicit multi-item orders cannot be split after their first
item is placed. Planned and actual container counts and stop fragmentation are
reported separately, together with preferred hits, fallbacks, and moved groups.
COG, support, LIFO, and replay remain construction-policy and independent
Level 1--8 validation responsibilities.

The pipeline ranks this candidate alongside compact and delivery-priority
candidates by validity, used-container count, then cost. Assignment failure or
timeout cannot replace a valid baseline. FFD remains unchanged as the fast
comparator in this checkpoint.

## Inactive

- SimPy or wall-clock event execution and route optimization;
- delivery-aware metaheuristic solvers beyond bounded local repair;
- exact removal-sequence optimization;
- loading order, handling equipment, time, staging space, and door geometry;
- vehicle axle/floor-zone constraints, dynamic transport loads, and vehicle
  certification.
### Bounded container elimination

Sau khi chọn được một nghiệm qua toàn bộ validator Level 1--8, runtime có thể
thử đóng các container ít tải trong một ngân sách riêng. Search di chuyển
nguyên support closure sang **các container đang mở**, không được mở container
khác và chỉ nhận thay đổi khi independent validator Level 1--8 vẫn `VALID`.
Metadata `delivery_container_elimination_*` phân biệt rõ container đã đóng,
hết thời gian và trường hợp không có phép loại bỏ hợp lệ. Việc thất bại ở pha
này không làm nghiệm ban đầu mất tính hợp lệ.

Nếu relocation closure trực tiếp thất bại, conflict-neighborhood LNS tháo một
tập support-component có giới hạn ở các container nhận rồi xếp lại đồng thời
với hàng từ container cần đóng. Neighborhood mặc định `4/8/12`, candidate cap
và deadline đều lấy từ config. Nó không full-rebuild instance, không tách
support component và không được chấp nhận nếu full Level 1--8 validation lỗi.
