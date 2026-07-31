# Level 8 sequential scale baseline

## Status

`PASS_WITH_BOUNDED_300_CONSTRUCTION_TIMEOUT`

This is an R&D reproducibility baseline, not a transport certification report.
The practical validated scale in this checkpoint is 100 selected items.
The 300-item experiment demonstrates bounded, fail-safe termination; it does
not demonstrate a valid 300-item packing.

## Reproducible source

- Synthetic profile: `level_08_scale_1000_c80_v1`
- Profile seed: `8080`
- Source items: `1000`
- Source containers: `80`
- Declared delivery stops: `40`
- Item CSV SHA-256:
  `7d0c8b8c98a62709d1df3a443d9ad3cbda22bd3c6653a2b90e72f9fa8ad5326d`
- Container CSV SHA-256:
  `fe1b864005ac634d67a986e8a905ee0e22bfa3a9274a082cc37793abacfefea6`

## Required 100-item gate

Benchmark:
`20260731T053114054794Z__level_08__benchmark__seed42`

| Scenario | Selection checksum | Runs | Result | Containers | Objective | Mean runtime |
|---|---|---:|---|---:|---:|---:|
| prefix 100/10 | `ec189c757bfce9c1994d8490c1e04140a16ac38a3a029057b0939db29cd485bf` | 2 | `FEASIBLE + VALID` | 3 | 35843 | 7.935 s |
| stable-random 101, 100/10 | `fb70a56ae4a3fb3c6ec3f227f5a830a1227f94c373ca464d2888847c06724f67` | 2 | `FEASIBLE + VALID` | 3 | 35763 | 3.734 s |

Both profiles have one placement signature across their two repeats. Their
selection checksums differ, so stable-random is no longer a permutation of the
same complete 100-row source.

## Bounded 300-item observation

Benchmark:
`20260731T060252773947Z__level_08__benchmark__seed42`

| Scenario | Selection checksum | Best Fit | FFD | Runtime per run |
|---|---|---|---|---:|
| prefix 300/25 | `63d3061b0339bed480a5afacdb3668c96ddc58984c2e84f356431d145fc131e6` | construction `TIME_LIMIT` | construction `TIME_LIMIT` | about 45.000 s |
| stable-random 101, 300/25 | `b1da644a4375cda0a565c504a4746adf0f17c35d77e57cec3e33a716d69cfea0` | construction `TIME_LIMIT` | construction `TIME_LIMIT` | about 45.000 s |
| stable-random 202, 300/25 | `8c3d5eabf5d4eaae56c4343678d90a22be87c13ad3a1c717546c762f189ad09a` | construction `TIME_LIMIT` | construction `TIME_LIMIT` | about 45.000 s |
| stable-random 303, 300/25 | `5c2f415ad7f059d94313eb2cc962f707c78e0fbac6aed5379a4caa3f18227039` | construction `TIME_LIMIT` | construction `TIME_LIMIT` | about 45.000 s |

All four scenario checksums are distinct and are shared by Best Fit and FFD
within each scenario. Every timeout has:

- `objective_value: null`;
- `delivery_repair_termination_reason: construction_time_limit`;
- `sequential_simulation_status: SKIPPED`;
- input, manifest, log, metrics, and solver status evidence only;
- no partial solution or simulation artifact bundle.

The strong reverse-loading COG construction evaluated roughly 1.9–2.1 million
candidate points per Best Fit profile before its deadline. Improving
300-item success therefore requires construction indexing/search work; replay
optimization alone cannot address this baseline.

## Checkpoint conclusion

Level 8 is closed as a validated deterministic sequential replay workflow up
to the required 100-item research gate, with explicit bounded behavior at
300 items. It must not be described as a production-certified loading system
or as a successful 300-item solver.

Future work should begin with the next approved level contract. Further Level
8 scale optimization remains a separate R&D track and must preserve all
independent Level 1–8 validators.
