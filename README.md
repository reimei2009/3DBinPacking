# 3D Container Packing

Project thử nghiệm đa level/đa thuật toán. `level_01` hiện chạy được `milp_big_m` (exact), `extreme_point_ffd` và `extreme_point_best_fit` (greedy constructive), `extreme_point_hill_climbing` (local search) và `extreme_point_simulated_annealing` (metaheuristic). Tất cả giữ orientation cố định, kiểm tra biên, non-overlap và payload. Level 1 không mô hình hóa rotation, support, stacking hay stability.

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

Chạy heuristic nhanh trên local:

```powershell
python scripts\run_experiment.py --level level_01 --algorithm extreme_point_ffd --items-count 50 --containers-count 8 --environment local --non-interactive
```

Chạy Best Fit — duyệt toàn bộ extreme point khả thi và chọn ứng viên theo container đang mở, chi phí tăng thêm, dung tích/tải trọng dư và bounding-volume growth:

```powershell
python scripts\run_experiment.py --level level_01 --algorithm extreme_point_best_fit --items-count 50 --containers-count 8 --environment local --non-interactive
```

`FEASIBLE` nghĩa là heuristic đã tìm thấy nghiệm qua validator, không phải bằng chứng tối ưu toàn cục.

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

Chạy một ma trận benchmark có thể tái lập:

```powershell
python scripts\run_benchmark.py --level level_01 --algorithms extreme_point_best_fit extreme_point_ffd extreme_point_hill_climbing extreme_point_simulated_annealing --item-counts 10 20 --container-counts 3 5 --seeds 7 11 19 23 29 --repeats 2
```

`--seeds` là các seed thí nghiệm khác nhau; `--repeats` là số lần đo lại cho từng seed. Ví dụ trên chạy `3 thuật toán × 2 item counts × 2 container counts × 5 seeds × 2 repeats = 120` case. Mỗi case tạo experiment run riêng. Bảng tổng hợp được lưu trong một benchmark run riêng dưới `outputs/level_01/runs/<benchmark_id>/benchmark/`.

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

Config rank 1 đã được lưu riêng, không ghi đè default:

```powershell
python scripts\run_experiment.py --config config/level_01/experiments/extreme_point_simulated_annealing_tuned_i20_c5_local.yaml --items-count 20 --containers-count 5 --seed 42 --non-interactive
```
