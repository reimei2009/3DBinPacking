# Level 3 — Xoay ngang

Trạng thái: **đã triển khai và đăng ký cho CLI/Streamlit/benchmark**.

Level 3 kế thừa toàn bộ geometry, payload, floor contact, exact base-support
ratio và base-center support của Level 2. Level này cho phép mỗi kiện giữ
chiều dài/rộng hoặc hoán đổi hai chiều ngang; chiều cao không đổi.

Với kiện `i`, tập hướng hợp lệ là `O_i` và phải chọn đúng một hướng:

```text
sum(o in O_i) r_io = 1
```

| Mã | Kích thước hiệu dụng `(length, width, height)` |
| --- | --- |
| `XYZ` | `(l_i, w_i, h_i)` |
| `YXZ` | `(w_i, l_i, h_i)` |

## Ràng buộc đang hoạt động

- chọn đúng một orientation được khai báo;
- boundary và non-overlap theo kích thước sau xoay;
- support footprint theo orientation;
- ghi orientation vào placement, scene, report và validation;
- bảo toàn behavior fixed-orientation của Level 1–2.

Không kích hoạt xoay làm thay đổi trục đứng, stackability, load-bearing,
nesting, fragility, balance hoặc loading/unloading order.

## Dữ liệu

Raw field `forced_orientation` được bảo toàn nhưng chưa có mapping semantics đã
xác minh. Solver không được đọc trực tiếp field này. Experiment hiện dùng
profile YAML tường minh:

- `fixed`: chỉ `XYZ`;
- `horizontal_rotatable`: `XYZ` và `YXZ`, loại hướng trùng khi length bằng
  width.

Profile synthetic phải ghi `orientation_profile_id`,
`allowed_orientation_codes` và `orientation_data_status` vào provenance.

## Solver

- `extreme_point_ffd`: constructive baseline;
- `extreme_point_best_fit`: practical candidate;
- Hill Climbing và Simulated Annealing: search comparator;
- Maximal Empty Spaces: geometric comparator;
- `milp_big_m`: exact reference giới hạn tối đa 5 items.

Mọi heuristic dùng cùng orientation provider và exact-support feasibility
policy. `INFEASIBLE_HEURISTIC` chỉ là thất bại tìm kiếm, không phải chứng minh
vô nghiệm.

## Nghiệm thu

Independent validator tính lại kích thước hiệu dụng từ orientation đã chọn,
sau đó kiểm tra toàn bộ contract Level 1–2. Nghiệm chỉ có official objective
khi complete và `VALID`.

Chạy exact reference nhỏ:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_experiment.py `
  --level level_03 `
  --algorithm milp_big_m `
  --config config\level_03\experiments\milp_big_m_reference.yaml `
  --non-interactive --preview-limit 0
```

Chạy benchmark heuristic thủ công:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_benchmark.py `
  --suite config\level_03\benchmarks\core_heuristics_local.yaml
```

Baseline và giới hạn scale được ghi tại
`docs/reports/manual/level_03_heuristic_acceptance.md`.
