# Level 7 scale baseline

This is an R&D balance baseline. The synthetic COG band is not a vehicle-certification standard.

## Promotion gates

- [x] `six_frozen_profiles_present`
- [x] `two_repeats_per_profile`
- [x] `all_runs_independently_valid`
- [x] `invalid_runs_have_no_objective`
- [x] `runtime_within_45_seconds`
- [x] `container_count_within_level6_plus_one`
- [x] `deterministic_signature_objective_and_cog`
- [x] `outcome_class_is_explicit`

**Primary acceptance:** PASS

## Best Fit primary

| Scenario | Repeat | Valid | Containers | Objective | Runtime (s) | Min COG margin | Outcome |
|---|---:|:---:|---:|---:|---:|---:|---|
| practical_prefix_i100_c10 | 1 | yes | 5 | 73505.000 | 5.670 | 0.063151 | VALID_FIXED_CONTAINER |
| practical_prefix_i100_c10 | 2 | yes | 5 | 73505.000 | 7.380 | 0.063151 | VALID_FIXED_CONTAINER |
| practical_prefix_i300_c25 | 1 | yes | 5 | 325205.000 | 5.241 | 0.008080 | VALID_FIXED_CONTAINER |
| practical_prefix_i300_c25 | 2 | yes | 5 | 325205.000 | 4.534 | 0.008080 | VALID_FIXED_CONTAINER |
| random_101_i300_c25 | 1 | yes | 6 | 389796.000 | 7.704 | 0.008209 | VALID_FIXED_CONTAINER |
| random_101_i300_c25 | 2 | yes | 6 | 389796.000 | 6.558 | 0.008209 | VALID_FIXED_CONTAINER |
| random_202_i300_c25 | 1 | yes | 5 | 325205.000 | 3.603 | 0.017927 | VALID_FIXED_CONTAINER |
| random_202_i300_c25 | 2 | yes | 5 | 325205.000 | 3.576 | 0.017927 | VALID_FIXED_CONTAINER |
| random_303_i300_c25 | 1 | yes | 5 | 325205.000 | 2.117 | 0.015753 | VALID_FIXED_CONTAINER |
| random_303_i300_c25 | 2 | yes | 5 | 325205.000 | 2.157 | 0.015753 | VALID_FIXED_CONTAINER |
| smoke_prefix_i20_c5 | 1 | yes | 2 | 11112.000 | 0.020 | 0.070689 | VALID_FIXED_CONTAINER |
| smoke_prefix_i20_c5 | 2 | yes | 2 | 11112.000 | 0.020 | 0.070689 | VALID_FIXED_CONTAINER |

## FFD fast comparator

FFD is a comparator; its quality is lower on some profiles but it does not block Best Fit promotion.

| Scenario | Repeat | Valid | Containers | Objective | Runtime (s) | Min COG margin | Outcome |
|---|---:|:---:|---:|---:|---:|---:|---|
| practical_prefix_i100_c10 | 1 | yes | 6 | 87496.000 | 12.282 | 0.057542 | VALID_FIXED_CONTAINER |
| practical_prefix_i300_c25 | 1 | yes | 6 | 389796.000 | 1.920 | 0.004538 | VALID_FIXED_CONTAINER |
| random_101_i300_c25 | 1 | yes | 7 | 451537.000 | 5.297 | 0.008209 | VALID_WITH_ONE_EXTRA_CONTAINER |
| random_202_i300_c25 | 1 | yes | 6 | 389796.000 | 4.785 | 0.000824 | VALID_FIXED_CONTAINER |
| random_303_i300_c25 | 1 | yes | 5 | 325205.000 | 2.534 | 0.008178 | VALID_FIXED_CONTAINER |
| smoke_prefix_i20_c5 | 1 | yes | 2 | 11112.000 | 0.014 | 0.070689 | VALID_FIXED_CONTAINER |

## Outcome contract

- `VALID_FIXED_CONTAINER`
- `VALID_WITH_ONE_EXTRA_CONTAINER`
- `NO_VALID_BALANCED_SOLUTION_WITHIN_BUDGET`

Invalid candidates have no objective value and are excluded from objective comparisons.
