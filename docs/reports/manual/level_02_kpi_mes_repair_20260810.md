# Evidence KPI/MES/repair — Level 2

- Objective chính thức: `(used_container_count, total_container_cost)`.
- `encoded_solver_objective` chỉ để tương thích artifact cũ, không dùng xếp hạng.
- Tất cả run thành công: `True`; deterministic: `True`.

## Promotion policy

| Hạng mục | Kết quả |
|---|---|
| kpi_promotion | `PENDING_KPI_500_GATE` |
| mes_fast_comparator | `PASS` |
| repair_fallback | `PASS` |

## So sánh official objective

| Nhóm | Algorithm | Items | Selection | Kết quả | Runtime ratio |
|---|---|---:|---|---|---:|
| KPI | extreme_point_best_fit | 100 | stable_random | TIE | 1.146 |
| KPI | extreme_point_best_fit | 300 | stable_random | WIN | 1.707 |
| KPI | maximal_space_best_fit | 100 | stable_random | TIE | 1.056 |
| KPI | maximal_space_best_fit | 300 | stable_random | WIN | 1.445 |
| Repair | extreme_point_best_fit | 100 | stable_random | TIE | 3.958 |
| Repair | extreme_point_best_fit | 300 | stable_random | WIN | 22.229 |
| Repair | extreme_point_best_fit | 500 | stable_random | WIN | 11.710 |
| Repair | maximal_space_best_fit | 100 | stable_random | TIE | 2.576 |
| Repair | maximal_space_best_fit | 300 | stable_random | WIN | 21.630 |
| Repair | maximal_space_best_fit | 500 | stable_random | WIN | 22.868 |

## MES

- p95 runtime ratio MES/Best Fit: `0.769`.
