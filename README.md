# 3D Container Packing

Project thử nghiệm đa level/đa thuật toán. `level_01` chạy MILP, constructive heuristic, local search và metaheuristic với orientation cố định. `level_02` kế thừa Level 1 và thêm floor contact, tỷ lệ hỗ trợ đáy cùng hỗ trợ tâm đáy. Level 2 dùng MILP làm exact reference và dùng chung năm engine heuristic/metaheuristic với exact-support feasibility policy. Level 2 vẫn chưa mô hình hóa rotation, stackability, truyền tải, độ bền chịu tải hoặc ổn định vật lý đầy đủ.

## Web 3D R&D

Ứng dụng Streamlit là một UI mỏng dùng chung pipeline với CLI và notebook. Logic solver, validator và scene generation vẫn nằm trong package Python nên có thể tái sử dụng khi chuyển sang FastAPI/React.

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install -e .
python scripts\run_web_app.py
```

Mở URL Streamlit in trong terminal, thường là `http://localhost:8501`. UI mặc định dùng tiếng Việt và có thể chuyển sang English. Giao diện cho phép chọn level, thuật toán, số item, số container, seed và tham số thuật toán; đồng thời dùng LaTeX để hiển thị ký hiệu, biến, hàm mục tiêu, ràng buộc, code mapping, validation, utilization và mô hình Plotly 3D. Trình xem 3D có các chế độ Rõ khối/Cân bằng/X-Ray, slider opacity, highlight và ẩn item. Xem [hướng dẫn web](docs/guides/running_web_app.md) và [kiến trúc tái sử dụng](docs/design/visualization_web_architecture.md).

Quy trình branch/worktree của dự án được mô tả tại `docs/design/git_workflow.md`: `main` ổn định, `develop` tích hợp, và branch ngắn hạn theo scope như `experiment/level-01/<task>`.

## Chạy thủ công

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
python -m container_packing.cli list
python scripts\run_experiment.py --interactive
```

Lệnh tương tác hỏi level, thuật toán, số item, số container và môi trường. Terminal hiển thị ngay status, validation, container được chọn, tải/thể tích, runtime, tọa độ placement và run directory.

Chạy không tương tác:

```powershell
python scripts\run_experiment.py --level level_01 --algorithm milp_big_m --items-count 10 --containers-count 3 --environment local --non-interactive
```

Level 5 dùng `extreme_point_best_fit` làm solver mặc định,
`extreme_point_ffd` làm constructive comparator và Hill Climbing làm
local-search comparator; Simulated Annealing là quality comparator cho tải tĩnh
đệ quy. Sức chịu tải mặc định dùng profile nghiên cứu
`synthetic_weight_factor_v1` (`M_i = 4w_i`), không phải thông số vật liệu thực:

```powershell
python scripts\run_experiment.py --level level_05 --items-count 10 --containers-count 3 --environment local --non-interactive
```

Output riêng nằm dưới `outputs/level_05/runs/<run_id>/`, gồm
`load_bearing.csv`, `load_transfer.csv` và
`load_bearing_validation.json`. Level 5 chưa mô hình hóa áp suất, mô-men,
biến dạng, tải động hoặc ổn định cơ học đầy đủ.

Level 5 SA sensitivity sweep là tác vụ dài và chạy thủ công:

```powershell
python scripts\run_parameter_sweep.py --config config\level_05\sweeps\sa_prefix_i20_c5_local.yaml
python scripts\run_parameter_sweep.py --config config\level_05\sweeps\sa_stable_random_101_i20_c5_local.yaml
```

Level 5 quality profile đã chọn SA p006 (`200`, `0.05`, `0.99`). Nghiệm thu
portfolio Best Fit/Hill/SA chạy thủ công:

```powershell
python scripts\run_benchmark.py --suite config\level_05\benchmarks\portfolio_local.yaml
```

Baseline đã nghiệm thu được ghi tại
`docs/reports/manual/level_05_portfolio_baseline_20260724.md`.

Chạy Level 2 support-only trên instance nhỏ:

```powershell
python scripts\run_experiment.py --level level_02 --items-count 20 --containers-count 5 --environment local --non-interactive
```

Level 2 mặc định chạy `extreme_point_ffd` với role `practical_default`. MILP
được giữ làm exact reference:

```powershell
python scripts\run_experiment.py --level level_02 --config config\level_02\experiments\milp_big_m_reference.yaml --non-interactive
```

Level 2 mặc định dùng grid MILP 4×4, threshold 0.80 và validator exact
union-area. Xem `solution/support.csv`; không hiểu support hình học là bằng
chứng ổn định cơ học.

Chạy Level 2 thực dụng bằng heuristic support-aware:

```powershell
python scripts\run_experiment.py --level level_02 --algorithm extreme_point_best_fit --items-count 20 --containers-count 5 --environment local --non-interactive
```

Các heuristic kiểm tra exact union support khi sinh từng candidate. MILP vẫn là
phương pháp tham chiếu; `FEASIBLE_TIME_LIMIT` không phải chứng minh tối ưu.

Chạy heuristic nhanh trên local:

```powershell
python scripts\run_experiment.py --level level_01 --algorithm extreme_point_ffd --items-count 50 --containers-count 8 --environment local --non-interactive
```

Chạy Best Fit — duyệt toàn bộ extreme point khả thi và chọn ứng viên theo container đang mở, chi phí tăng thêm, dung tích/tải trọng dư và bounding-volume growth:

```powershell
python scripts\run_experiment.py --level level_01 --algorithm extreme_point_best_fit --items-count 50 --containers-count 8 --environment local --non-interactive
```

`FEASIBLE` nghĩa là heuristic đã tìm thấy nghiệm qua validator, không phải bằng chứng tối ưu toàn cục.

Chạy Maximal Empty Spaces — biểu diễn phần trống bằng các khối hộp cực đại và chọn vị trí Best Fit:

```powershell
python scripts\run_experiment.py --level level_01 --algorithm maximal_space_best_fit --items-count 50 --containers-count 8 --environment local --non-interactive
```

Chạy Hill Climbing:

```powershell
python scripts\run_experiment.py --level level_01 --algorithm extreme_point_hill_climbing --items-count 50 --containers-count 8 --environment local --non-interactive
```

Chạy Simulated Annealing có seed, phù hợp local CPU:

```powershell
python scripts\run_experiment.py --level level_01 --algorithm extreme_point_simulated_annealing --items-count 50 --containers-count 8 --environment local --non-interactive
```

Override seed cho một run bằng `--seed 7`. Seed thực tế được lưu trong run ID, manifest và resolved config.

Mặc định terminal hiển thị 20 placement đầu. Dùng `--preview-limit 5`, `--preview-limit 0`, hoặc `--json-only`.

Output đầy đủ nằm tại `outputs/<level_id>/runs/<run_id>/`. Xem hướng dẫn chi tiết ở `docs/guides/manual_test_flow.md`.

## Benchmark

Chạy bộ instance Level 1 chuẩn (MILP chỉ chạy case nhỏ; các phương pháp nhẹ
chạy thêm các profile random, đa dạng thể tích, nặng tải và lớn thể tích):

```powershell
python scripts\run_benchmark.py --suite config\level_01\benchmarks\core_local.yaml
```

Mỗi scenario lưu chiến lược chọn item, seed chọn tập, danh sách ID, checksum và
thống kê profile. Vì vậy chỉ các dòng có cùng `scenario_id` và
`input_fingerprint` mới được so sánh trực tiếp.

Chạy một ma trận benchmark có thể tái lập:

```powershell
python scripts\run_benchmark.py --level level_01 --algorithms extreme_point_best_fit extreme_point_ffd maximal_space_best_fit extreme_point_hill_climbing extreme_point_simulated_annealing --item-counts 10 20 --container-counts 3 5 --seeds 7 11 19 23 29 --repeats 2
```

`--seeds` là các seed thí nghiệm khác nhau; `--repeats` là số lần đo lại cho từng seed. Ví dụ trên chạy `5 thuật toán × 2 item counts × 2 container counts × 5 seeds × 2 repeats = 200` case. Mỗi case tạo experiment run riêng. Bảng tổng hợp được lưu trong một benchmark run riêng dưới `outputs/level_01/runs/<benchmark_id>/benchmark/`.

Sau mỗi benchmark, xem `ranking.csv` (xếp hạng Level 1: hợp lệ → ít
container → chi phí → runtime), `pairwise_comparison.csv`,
`pareto_frontier.csv`, và `milp_reference_gaps.csv`. File cuối chỉ có ý nghĩa
khi MILP đã chứng minh `OPTIMAL` cho toàn bộ lần chạy cùng scenario.

## Parameter sweep

Chạy grid mặc định cho Simulated Annealing:

```powershell
python scripts\run_parameter_sweep.py --config config/level_01/sweeps/extreme_point_simulated_annealing_local.yaml
```

Override quy mô và seed mà không sửa YAML:

```powershell
python scripts\run_parameter_sweep.py --item-counts 20 30 --container-counts 5 --seeds 7 11 19 --repeats 1
```

Grid YAML hiện so sánh `initial_temperature`, `cooling_rate` và `max_iterations`. Kết quả đầy đủ nằm tại `outputs/level_01/runs/<sweep_id>/sweep/`; xem `ranking.csv` và `best_parameters.json`. Rank 1 chỉ là tốt nhất trong grid/instance/seed đã thử, không phải bằng chứng tối ưu toàn cục.

Level 2 cũng có sweep cấu hình cho ngưỡng support $\alpha$ của FFD. Lệnh này
chạy thủ công vì tạo chín experiment run:

```powershell
python scripts\run_parameter_sweep.py --config config\level_02\sweeps\support_threshold_local.yaml
```

`sweep.config_parameters` dùng đường dẫn config như `support.threshold`; mọi
giá trị được lưu trong resolved config của từng run.

Config rank 1 đã được lưu riêng, không ghi đè default:

```powershell
python scripts\run_experiment.py --config config/level_01/experiments/extreme_point_simulated_annealing_tuned_i20_c5_local.yaml --items-count 20 --containers-count 5 --seed 42 --non-interactive
```
