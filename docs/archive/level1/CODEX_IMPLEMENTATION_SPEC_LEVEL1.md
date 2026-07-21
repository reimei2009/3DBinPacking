# ĐẶC TẢ THỰC THI CHO CODEX
## Level 1 — Hệ thống xếp kiện 3D vào nhiều container khác nhau

> Tài liệu này là yêu cầu triển khai hoàn chỉnh. Codex phải đọc toàn bộ tài liệu, kiểm tra các file hiện có, sau đó tự tạo project, viết code, chạy thử, sửa lỗi và chỉ kết thúc khi các tiêu chí nghiệm thu ở cuối tài liệu đều đạt.

---

# 1. Mục tiêu của project

Xây dựng phiên bản cơ bản nhất của bài toán **3D Bin Packing Problem với nhiều container không đồng nhất**.

Hệ thống nhận:

- một tập kiện hình hộp chữ nhật;
- năm container vật lý có kích thước, tải trọng và chi phí khác nhau;
- toàn bộ dữ liệu được biết trước khi giải.

Hệ thống phải quyết định:

1. Container nào được sử dụng.
2. Mỗi kiện được gán vào container nào.
3. Tọa độ đặt của mỗi kiện trong container.
4. Bảo đảm kiện không vượt biên.
5. Bảo đảm các kiện không chồng lấn thể tích.
6. Bảo đảm tổng khối lượng trong mỗi container không vượt tải trọng.
7. Tối thiểu số container; nếu bằng nhau thì tối thiểu tổng chi phí container.

Đây là **Level 1**. Không tự ý thêm ràng buộc nâng cao.

---

# 2. Phạm vi Level 1

## 2.1. Bắt buộc triển khai

- Offline packing: biết toàn bộ kiện trước khi giải.
- Kiện là hình hộp chữ nhật.
- Container là hình hộp chữ nhật.
- Tất cả cạnh song song với ba trục tọa độ.
- Mỗi kiện phải được xếp đúng một lần.
- Không xoay kiện trong Level 1.
- Không được vượt biên container.
- Không được giao nhau theo thể tích.
- Không được vượt tải trọng container.
- Có năm container khác nhau.
- Mỗi container chỉ có một bản vật lý trong bộ thử nghiệm.
- Hàm mục tiêu ưu tiên số container trước chi phí.
- Solver chính xác bằng Mixed Integer Linear Programming.
- Phải có bước kiểm tra nghiệm độc lập sau solver.

## 2.2. Tuyệt đối chưa triển khai

Không thêm các yêu cầu sau, trừ khi người dùng yêu cầu nâng level:

- rotation hoặc orientation;
- `forced_orientation`;
- nesting;
- `nesting_height`;
- stackability;
- `stackability_code`;
- `max_stackability`;
- kiện phải nằm trên sàn hoặc được kiện khác đỡ;
- diện tích tiếp xúc tối thiểu;
- tải trọng truyền qua các kiện;
- hàng dễ vỡ;
- trọng tâm;
- cân bằng tải theo trục;
- thứ tự bốc/dỡ;
- cửa container;
- hàng nguy hiểm hoặc không tương thích;
- online packing;
- nhiều bản sao của một loại container;
- tối ưu heuristic cho hàng trăm kiện.

Các cột nâng cao vẫn được giữ trong CSV để phục vụ Level sau, nhưng không được dùng trong model Level 1.

---

# 3. Các file đầu vào hiện có

Các file được cung cấp cùng tài liệu này:

```text
containers_level1_5types.csv
scidb_3dbppsi_items_level1_20.csv
level1_3dbppsi_milp.ipynb
level1_3dbppsi_milp_executed.ipynb
level1_3dbppsi_mathematical_model.md
level1_optimal_solution.csv
level1_container_summary.csv
level1_3dbppsi_bundle.zip
```

Ý nghĩa:

| File | Vai trò |
|---|---|
| `containers_level1_5types.csv` | Năm container tổng hợp dùng cho Level 1 |
| `scidb_3dbppsi_items_level1_20.csv` | 20 kiện lấy từ benchmark 3DBPPsi |
| `level1_3dbppsi_milp.ipynb` | Notebook sạch chứa implementation tham chiếu |
| `level1_3dbppsi_milp_executed.ipynb` | Notebook đã chạy và có output kiểm chứng |
| `level1_3dbppsi_mathematical_model.md` | Mô tả mô hình toán hiện tại |
| `level1_optimal_solution.csv` | Tọa độ nghiệm đã kiểm chứng |
| `level1_container_summary.csv` | Tổng hợp mức sử dụng container |
| `level1_3dbppsi_bundle.zip` | Gói dữ liệu và notebook đầy đủ |

## Quy tắc quan trọng

- Không chỉnh sửa trực tiếp dữ liệu gốc trong `data/raw`.
- Dữ liệu dùng để chạy phải đặt trong `data/processed`.
- Notebook hiện có là tài liệu tham chiếu, không phải kiến trúc code cuối cùng.
- Codex phải đọc notebook trước khi viết lại project.
- Không xóa notebook.
- Không thay đổi mục tiêu và giả định Level 1.

---

# 4. Nguồn dữ liệu

## 4.1. Trang Science Data Bank do người dùng cung cấp

```text
https://www.scidb.cn/en/detail?dataSetId=d290275c2f3142ed967acc479723cbd1#p1
```

## 4.2. Repository công khai chứa code và dữ liệu benchmark

```text
https://github.com/MRVSmartNetworks/container_loading_heuristics
```

Thư mục dữ liệu tham chiếu:

```text
data/dataset_small/
```

Các file gốc đã được đóng trong bundle:

```text
dataset_small_items_original.csv
dataset_small_vehicles_original.csv
```

Level 1 hiện chỉ lấy 20 kiện đầu tiên từ file items gốc và tạo riêng 5 container tổng hợp.

## 4.3. Quy tắc về tính trung thực dữ liệu

Phải ghi rõ trong README và metadata đầu ra:

- Dữ liệu kiện có nguồn từ benchmark công khai.
- Năm container Level 1 là dữ liệu tổng hợp.
- `cost` là điểm chi phí so sánh tổng hợp, không phải giá vận chuyển thực tế.
- Kết quả Level 1 không phải kết quả benchmark chính thức của paper.

---

# 5. Cấu trúc project bắt buộc

Codex phải tạo cấu trúc sau:

```text
3d-container-packing-level1/
│
├── README.md
├── requirements.txt
├── .gitignore
├── pyproject.toml                  # tùy chọn nhưng khuyến khích
│
├── config/
│   └── level1.yaml
│
├── data/
│   ├── raw/
│   │   ├── dataset_small_items_original.csv
│   │   └── dataset_small_vehicles_original.csv
│   │
│   └── processed/
│       ├── items_level1_20.csv
│       └── containers_level1_5types.csv
│
├── notebooks/
│   ├── level1_3dbppsi_milp.ipynb
│   └── level1_3dbppsi_milp_executed.ipynb
│
├── src/
│   └── container_packing/
│       ├── __init__.py
│       ├── constants.py
│       ├── schemas.py
│       ├── data_loader.py
│       ├── preprocessing.py
│       ├── model_indices.py
│       ├── milp_model.py
│       ├── solver.py
│       ├── validation.py
│       ├── reporting.py
│       └── cli.py
│
├── scripts/
│   ├── prepare_level1_data.py
│   ├── run_level1.py
│   └── validate_solution.py
│
├── tests/
│   ├── test_data_loader.py
│   ├── test_model_indices.py
│   ├── test_geometry.py
│   ├── test_validation.py
│   └── test_level1_integration.py
│
├── outputs/
│   ├── .gitkeep
│   ├── placements.csv             # sinh sau khi chạy
│   ├── container_summary.csv      # sinh sau khi chạy
│   ├── run_metadata.json          # sinh sau khi chạy
│   └── validation_report.json     # sinh sau khi chạy
│
└── docs/
    ├── mathematical_model.md
    ├── data_dictionary.md
    └── level1_limitations.md
```

Nếu tên thư mục project hiện tại khác, vẫn phải giữ cấu trúc con tương đương.

---

# 6. Môi trường chạy

## 6.1. Phiên bản khuyến nghị

- Python 3.11 hoặc 3.12 được khuyến nghị cho máy cá nhân.
- Bản notebook tham chiếu đã được kiểm tra bằng:
  - Python 3.13.5;
  - NumPy 2.3.5;
  - SciPy 1.17.0.

Không được viết code phụ thuộc riêng vào Python 3.13 nếu không cần thiết.

## 6.2. `requirements.txt`

Tạo file:

```text
numpy>=1.26,<3
scipy>=1.11,<2
pandas>=2.2,<3
jupyterlab>=4,<5
nbformat>=5.10,<6
nbclient>=0.10,<1
matplotlib>=3.8,<4
pytest>=8,<10
PyYAML>=6,<7
```

Level 1 không cần Gurobi, CPLEX hoặc OR-Tools.

## 6.3. Cài đặt trên Windows PowerShell

```powershell
cd <duong-dan-den-project>

py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements.txt

python -c "import numpy, scipy; print(numpy.__version__, scipy.__version__)"
```

Nếu PowerShell chặn activate:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

## 6.4. Cài đặt trên Windows CMD

```bat
cd <duong-dan-den-project>
py -3.12 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## 6.5. Cài đặt trên Linux hoặc macOS

```bash
cd <project-directory>
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

---

# 7. Cấu hình Level 1

Tạo `config/level1.yaml`:

```yaml
project:
  name: 3d-container-packing-level1
  random_seed: 42

paths:
  items_csv: data/processed/items_level1_20.csv
  containers_csv: data/processed/containers_level1_5types.csv
  output_dir: outputs

model:
  allow_rotation: false
  enforce_stability: false
  enforce_stackability: false
  require_all_items: true
  objective:
    primary: minimize_container_count
    secondary: minimize_container_cost

solver:
  backend: scipy_highs
  time_limit_seconds: 600
  mip_rel_gap: 0.0
  presolve: true
  display: true

validation:
  coordinate_tolerance_mm: 0.0001
  weight_tolerance_kg: 0.000001
```

Code không được hard-code đường dẫn `/mnt/data`.

Tất cả đường dẫn phải được giải quyết tương đối từ project root hoặc nhận qua CLI.

---

# 8. Schema dữ liệu kiện

File đích:

```text
data/processed/items_level1_20.csv
```

Các cột:

| Cột | Kiểu | Bắt buộc | Dùng trong Level 1 | Mô tả |
|---|---:|---:|---:|---|
| `level1_order` | int | Có | Có | Thứ tự thử nghiệm |
| `id_item` | str | Có | Có | ID duy nhất |
| `length_mm` | int/float | Có | Có | Chiều dài |
| `width_mm` | int/float | Có | Có | Chiều rộng |
| `height_mm` | int/float | Có | Có | Chiều cao |
| `weight_kg` | float | Có | Có | Khối lượng |
| `nesting_height_mm` | int/float | Có | Không | Giữ cho Level sau |
| `stackability_code` | str/int | Có | Không | Giữ cho Level sau |
| `forced_orientation` | str | Có | Không | Giữ cho Level sau |
| `max_stackability` | int | Có | Không | Giữ cho Level sau |
| `used_in_level1` | int/bool | Có | Dùng lọc | 1 nếu dùng |
| `level1_note` | str | Không | Không | Ghi chú |
| `source_url` | str | Không | Không | Nguồn |

## Kiểm tra bắt buộc

- `id_item` không được trùng.
- Kích thước phải dương.
- Khối lượng phải dương.
- Không có `NaN` trong trường Level 1.
- Có đúng 20 kiện trong instance mặc định.
- Mỗi kiện phải vừa ít nhất một container theo đúng orientation hiện tại.
- Không được tự động xoay `length` và `width`.

---

# 9. Schema dữ liệu container

File đích:

```text
data/processed/containers_level1_5types.csv
```

Các cột:

| Cột | Kiểu | Bắt buộc | Mô tả |
|---|---:|---:|---|
| `container_id` | str | Có | ID duy nhất |
| `length_mm` | int/float | Có | Chiều dài trong |
| `width_mm` | int/float | Có | Chiều rộng trong |
| `height_mm` | int/float | Có | Chiều cao trong |
| `max_weight_kg` | float | Có | Tải trọng tối đa |
| `availability` | int | Có | Level 1 mặc định bằng 1 |
| `cost` | float | Có | Chi phí tổng hợp |
| `volume_m3` | float | Có | Thể tích kiểm tra |
| `data_status` | str | Có | `synthetic_level1` |
| `unit_note` | str | Không | Ghi chú đơn vị |
| `design_note` | str | Không | Ghi chú nguồn |

Dữ liệu mặc định:

| ID | L mm | W mm | H mm | Tải kg | Chi phí |
|---|---:|---:|---:|---:|---:|
| C1 | 3000 | 2200 | 2200 | 1500 | 650 |
| C2 | 3600 | 2300 | 2300 | 2200 | 760 |
| C3 | 4200 | 2400 | 2400 | 3000 | 880 |
| C4 | 5000 | 2450 | 2600 | 4200 | 1050 |
| C5 | 6000 | 2500 | 2800 | 5500 | 1250 |

Kiểm tra:

```text
volume_m3 = length_mm * width_mm * height_mm / 1_000_000_000
```

Cho phép sai số làm tròn nhỏ.

---

# 10. Mô hình toán học bắt buộc

## 10.1. Tập chỉ số

- `I`: tập kiện, chỉ số `i`, `j`.
- `K`: tập container, chỉ số `k`.
- `P = {(i,j) | i < j}`: tập cặp kiện.
- `D = {LEFT, RIGHT, FRONT, BACK, BELOW, ABOVE}`.

## 10.2. Tham số kiện

- `l_i`: chiều dài kiện.
- `w_i`: chiều rộng kiện.
- `h_i`: chiều cao kiện.
- `q_i`: khối lượng kiện.

## 10.3. Tham số container

- `L_k`: chiều dài container.
- `W_k`: chiều rộng container.
- `H_k`: chiều cao container.
- `Q_k`: tải trọng container.
- `c_k`: chi phí container.

## 10.4. Biến quyết định

### Biến dùng container

```text
u_k ∈ {0,1}
```

`u_k = 1` nếu container `k` được dùng.

### Biến gán kiện

```text
a_ik ∈ {0,1}
```

`a_ik = 1` nếu kiện `i` nằm trong container `k`.

### Biến tọa độ

```text
x_i, y_i, z_i ≥ 0
```

Đây là góc dưới–trái–trước của kiện trong container được gán.

### Biến tách cặp kiện

Với mỗi `(i,j,k)` tạo sáu biến nhị phân:

```text
delta_left_ijk
delta_right_ijk
delta_front_ijk
delta_back_ijk
delta_below_ijk
delta_above_ijk
```

## 10.5. Hàm mục tiêu

Đặt:

```text
B = 1 + sum(cost_k for all containers)
```

Tối thiểu:

```text
B * sum(u_k) + sum(cost_k * u_k)
```

Với dữ liệu hiện tại:

```text
sum(cost) = 4590
B = 4591
```

Giảm một container luôn tốt hơn mọi chênh lệch chi phí.

## 10.6. Ràng buộc

### R1 — Mỗi kiện thuộc đúng một container

```text
sum_k a_ik = 1, for every item i
```

### R2 — Chỉ gán vào container đang dùng

```text
a_ik <= u_k
```

### R3 — Không vượt chiều dài

```text
x_i + l_i <= L_k + Mx * (1 - a_ik)
```

### R4 — Không vượt chiều rộng

```text
y_i + w_i <= W_k + My * (1 - a_ik)
```

### R5 — Không vượt chiều cao

```text
z_i + h_i <= H_k + Mz * (1 - a_ik)
```

Chọn:

```text
Mx = max(L_k)
My = max(W_k)
Mz = max(H_k)
```

### R6 — Tải trọng

```text
sum_i q_i * a_ik <= Q_k * u_k
```

### R7 — Biến quan hệ chỉ hoạt động khi cùng container

Với mọi hướng `d`:

```text
delta_d_ijk <= a_ik
delta_d_ijk <= a_jk
```

### R8 — Hai kiện cùng container phải có ít nhất một hướng tách

```text
sum_d delta_d_ijk >= a_ik + a_jk - 1
```

### R9 — Sáu bất đẳng thức không chồng lấn

```text
x_i + l_i <= x_j + Mx * (1 - delta_left_ijk)
x_j + l_j <= x_i + Mx * (1 - delta_right_ijk)

y_i + w_i <= y_j + My * (1 - delta_front_ijk)
y_j + w_j <= y_i + My * (1 - delta_back_ijk)

z_i + h_i <= z_j + Mz * (1 - delta_below_ijk)
z_j + h_j <= z_i + Mz * (1 - delta_above_ijk)
```

Không thêm ràng buộc support hoặc gravity.

---

# 11. Trách nhiệm từng module

## `schemas.py`

Dùng `dataclass` hoặc typed structures:

```python
Item
Container
Placement
ContainerUsage
ValidationIssue
SolveResult
```

Không bắt buộc dùng Pydantic.

## `data_loader.py`

- đọc CSV bằng `utf-8-sig` để xử lý BOM;
- chuyển kiểu rõ ràng;
- báo lỗi có tên file và số dòng;
- không silently bỏ dòng lỗi;
- kiểm tra ID trùng;
- kiểm tra số dương.

## `preprocessing.py`

- lọc `used_in_level1 == 1`;
- tính thể tích kiện;
- xác nhận mỗi kiện vừa ít nhất một container;
- không xoay kiện;
- không thay đổi thứ tự cột nguồn;
- hỗ trợ tham số `limit_items`, mặc định 20.

## `model_indices.py`

Quản lý ánh xạ biến sang cột vector MILP.

Phải cung cấp hàm rõ ràng thay vì rải tuple key khắp code:

```python
u(k)
a(i, k)
x(i)
y(i)
z(i)
delta(i, j, k, direction)
```

Phải có test bảo đảm:

- không trùng index;
- index liên tục từ `0` đến `n_vars - 1`;
- đúng số biến.

Với 20 kiện và 5 container:

```text
u: 5
a: 100
coordinates: 60
delta: 5700
total: 5865
```

## `milp_model.py`

Phải tạo:

- objective vector;
- integrality vector;
- lower bounds;
- upper bounds;
- sparse constraint matrix;
- lower constraint bounds;
- upper constraint bounds.

Dùng sparse matrix, không dùng dense matrix cho toàn mô hình.

Khuyến nghị:

```python
scipy.sparse.lil_matrix
```

khi xây dựng, sau đó chuyển sang:

```python
scipy.sparse.csr_matrix
```

trước khi gọi solver.

Phải có metadata:

```python
{
  "n_items": ...,
  "n_containers": ...,
  "n_pairs": ...,
  "n_variables": ...,
  "n_constraints": ...,
  "big_m": {"x": ..., "y": ..., "z": ...},
  "objective_priority_constant": ...
}
```

## `solver.py`

Dùng:

```python
scipy.optimize.milp
```

với:

```python
LinearConstraint
Bounds
```

Phải hỗ trợ:

- time limit;
- relative MIP gap;
- presolve;
- solver display.

Không được coi `result.success == False` là nghiệm hợp lệ.

Nếu time limit nhưng có nghiệm khả thi, chỉ lưu nghiệm khi SciPy trả vector nghiệm và phải ghi status là `FEASIBLE_TIME_LIMIT`, không ghi `OPTIMAL`.

## `validation.py`

Đây là bước bắt buộc và độc lập với model.

Phải kiểm tra:

1. Mỗi kiện xuất hiện đúng một lần.
2. Không có item ID lạ.
3. Không thiếu item.
4. Container ID tồn tại.
5. `x, y, z >= -tolerance`.
6. Kiện không vượt `L, W, H`.
7. Tổng tải không vượt `Q`.
8. Mọi cặp kiện trong cùng container không giao nhau.
9. Kích thước placement khớp dữ liệu input.
10. Khối lượng placement khớp dữ liệu input.

Hàm giao nhau dùng khoảng nửa kín hoặc kiểm tra tách:

```python
separated = (
    ax2 <= bx1 + eps or
    bx2 <= ax1 + eps or
    ay2 <= by1 + eps or
    by2 <= ay1 + eps or
    az2 <= bz1 + eps or
    bz2 <= az1 + eps
)
intersects = not separated
```

Hai kiện được phép chạm mặt, chạm cạnh hoặc chạm điểm.

Do solver có sai số floating point, tọa độ rất gần 0 phải được chuẩn hóa:

```python
if abs(value) < tolerance:
    value = 0.0
```

Không round thô trước validation. Chỉ round để xuất báo cáo sau khi nghiệm đã hợp lệ.

## `reporting.py`

Sinh:

### `outputs/placements.csv`

Cột tối thiểu:

```text
item_id
container_id
x_mm
y_mm
z_mm
length_mm
width_mm
height_mm
weight_kg
volume_m3
```

### `outputs/container_summary.csv`

Cột tối thiểu:

```text
container_id
used
item_count
loaded_weight_kg
max_weight_kg
weight_utilization_pct
loaded_volume_m3
container_volume_m3
volume_utilization_pct
cost
```

### `outputs/run_metadata.json`

Bao gồm:

```json
{
  "status": "OPTIMAL",
  "solver": "scipy.optimize.milp/HiGHS",
  "objective_value": 10992.0,
  "container_count": 2,
  "selected_containers": ["C2", "C4"],
  "total_container_cost": 1810.0,
  "n_items": 20,
  "n_containers_available": 5,
  "n_variables": 5865,
  "n_constraints": 18475,
  "level": 1,
  "rotation_enabled": false,
  "stability_enabled": false
}
```

Không hard-code các giá trị kết quả. Phải tính từ nghiệm; số trên chỉ là output mong đợi của instance tham chiếu.

### `outputs/validation_report.json`

```json
{
  "valid": true,
  "issue_count": 0,
  "issues": []
}
```

## `cli.py`

CLI tối thiểu:

```bash
python -m container_packing.cli solve --config config/level1.yaml
python -m container_packing.cli validate --config config/level1.yaml --solution outputs/placements.csv
```

Có thể dùng `argparse`; không cần thêm thư viện CLI.

---

# 12. Script thực thi

## `scripts/prepare_level1_data.py`

Nhiệm vụ:

- tìm file raw;
- đọc items gốc;
- lấy đúng 20 kiện đầu tiên theo thứ tự nguồn;
- thêm hoặc giữ metadata Level 1;
- ghi `data/processed/items_level1_20.csv`;
- sao chép hoặc tạo file 5 container;
- in thống kê:
  - số kiện;
  - tổng thể tích;
  - tổng khối lượng;
  - kích thước min/max;
  - kiện không vừa container nào.

Không được chạy solver trong script này.

## `scripts/run_level1.py`

Nhiệm vụ:

1. đọc config;
2. đọc dữ liệu;
3. validate input;
4. xây model;
5. in số biến/ràng buộc;
6. gọi solver;
7. trích xuất placement;
8. validate nghiệm;
9. chỉ ghi output cuối nếu validation hợp lệ;
10. trả exit code khác 0 nếu lỗi.

## `scripts/validate_solution.py`

Cho phép kiểm tra lại một file placement có sẵn:

```bash
python scripts/validate_solution.py \
  --items data/processed/items_level1_20.csv \
  --containers data/processed/containers_level1_5types.csv \
  --solution outputs/placements.csv
```

---

# 13. Cách chạy sau khi Codex hoàn thành

## 13.1. Chuẩn bị dữ liệu

```powershell
python scripts/prepare_level1_data.py
```

Đầu ra mong đợi gần tương tự:

```text
Prepared items: 20
Available containers: 5
Total item volume: 24.210 m3
Total item weight: 6228.728 kg
Invalid items: 0
```

## 13.2. Chạy solver

```powershell
python scripts/run_level1.py --config config/level1.yaml
```

Hoặc:

```powershell
python -m container_packing.cli solve --config config/level1.yaml
```

Nếu package nằm trong `src`, một trong các cách sau phải được cấu hình:

```powershell
pip install -e .
```

hoặc script phải tự thêm project `src` hợp lý. Ưu tiên `pip install -e .`.

## 13.3. Chạy test

```powershell
pytest -q
```

## 13.4. Chạy notebook

```powershell
jupyter lab
```

Mở:

```text
notebooks/level1_3dbppsi_milp.ipynb
```

Notebook phải dùng đường dẫn tương đối từ project root hoặc tự tìm root; không dùng `/mnt/data`.

---

# 14. Test bắt buộc

## 14.1. Unit test dữ liệu

- Đọc được BOM UTF-8.
- Phát hiện ID trùng.
- Phát hiện kích thước âm hoặc bằng 0.
- Phát hiện khối lượng âm hoặc bằng 0.
- Phát hiện thiếu cột.
- Phát hiện `volume_m3` container không khớp kích thước.

## 14.2. Unit test hình học

Các trường hợp:

- hai hộp tách theo X → không giao;
- tách theo Y → không giao;
- tách theo Z → không giao;
- chạm mặt → không giao;
- chạm cạnh → không giao;
- trùng một phần → giao;
- một hộp nằm hoàn toàn trong hộp khác → giao;
- cùng tọa độ → giao.

## 14.3. Test model index

Với `n=20`, `m=5`:

```text
n_pairs = 190
n_delta = 190 * 5 * 6 = 5700
n_vars = 5865
```

## 14.4. Integration test instance chính

Chạy solver trên dữ liệu 20 kiện.

Tiêu chí:

- solver tìm được nghiệm;
- validation hợp lệ;
- tất cả 20 kiện được xếp;
- số container bằng 2;
- container được chọn là `C2` và `C4`;
- tổng cost bằng `1810`;
- objective bằng `10992` trong sai số solver;
- không bắt buộc tọa độ phải giống từng số với file nghiệm tham chiếu, vì MILP có thể có nhiều nghiệm hình học tối ưu.

## 14.5. Test infeasible

Tạo container quá nhỏ hoặc tải quá thấp để không thể chứa một kiện.

Hệ thống phải:

- báo `INFEASIBLE`;
- không ghi `placements.csv` giả;
- trả exit code khác 0;
- ghi metadata lỗi rõ ràng.

## 14.6. Test một kiện

Một kiện vừa một container:

- dùng đúng một container;
- tọa độ hợp lệ;
- validation pass.

---

# 15. Kết quả tham chiếu

Trên instance 20 kiện hiện tại, notebook đã cho:

```text
Items: 20
Containers: 5
Total item volume: 24.210 m³
Total item weight: 6228.728 kg
Number of variables: 5865
Number of constraints: 18475
Optimization terminated successfully. (HiGHS Status 7: Optimal)
Objective: 10992.0
Used containers: ['C2', 'C4']
Container count: 2
Total cost: 1810.0
Validation problems: []
VALID LEVEL-1 SOLUTION
```

Tóm tắt tải:

### C2

```text
item_count: 9
loaded_weight_kg: 2150.272
max_weight_kg: 2200
weight_utilization_pct: khoảng 97.740
loaded_volume_m3: khoảng 7.381394
container_volume_m3: 19.044
volume_utilization_pct: khoảng 38.760
```

### C4

```text
item_count: 11
loaded_weight_kg: 4078.456
max_weight_kg: 4200
weight_utilization_pct: khoảng 97.106
loaded_volume_m3: khoảng 16.828919
container_volume_m3: 31.850
volume_utilization_pct: khoảng 52.838
```

Không hard-code vị trí hoặc thống kê vào code.

---

# 16. Lưu ý quan trọng về nghiệm

Model Level 1 chỉ bảo đảm hình học và tải trọng container.

Một kiện có thể có `z > 0` nhưng không có kiện thực tế bên dưới đỡ nó. Đây chưa phải lỗi của Level 1.

README phải ghi rõ:

> Nghiệm Level 1 có thể chứa kiện lơ lửng. Nghiệm chỉ hợp lệ theo ràng buộc biên, không giao nhau và tải trọng container; chưa hợp lệ theo ổn định vật lý.

Không tự ý “sửa” bằng cách ép tất cả kiện xuống sàn hoặc thêm support constraints.

---

# 17. README bắt buộc phải giải thích

README cuối phải có:

1. Bài toán là gì.
2. Phạm vi Level 1.
3. Nguồn dữ liệu.
4. Container là dữ liệu tổng hợp.
5. Cấu trúc project.
6. Cách tạo virtual environment.
7. Cách cài thư viện.
8. Cách chuẩn bị dữ liệu.
9. Cách chạy solver.
10. Cách chạy test.
11. Cách đọc output.
12. Kết quả tham chiếu.
13. Giới hạn Level 1.
14. Hướng mở rộng Level 2 nhưng không triển khai.

---

# 18. Quy tắc coding

- Python có type hints cho public functions.
- Docstring cho module và hàm quan trọng.
- Không dùng global mutable state.
- Không dùng `eval`.
- Không nuốt exception bằng `except: pass`.
- Thông báo lỗi phải chỉ ra file/cột/item liên quan.
- Không dùng absolute path riêng của máy.
- Không phụ thuộc notebook để CLI hoạt động.
- Không sửa dữ liệu gốc trong `data/raw`.
- Không lưu output vào `data`.
- Không hard-code kết quả tham chiếu.
- Dùng logging thay vì print rải rác trong module; script/CLI có thể in summary.
- Dùng sparse constraints.
- Không tạo DataFrame hàng triệu dòng cho biến cặp.
- Không tạo biểu đồ khi chưa được yêu cầu.
- Không triển khai giao diện web.
- Không triển khai database.

---

# 19. Thứ tự Codex phải thực hiện

Codex phải làm theo trình tự:

1. Liệt kê và đọc các file hiện có.
2. Mở notebook sạch và notebook executed.
3. Đọc CSV và xác nhận schema.
4. Tạo cây thư mục project.
5. Di chuyển/sao chép file vào đúng thư mục, không làm mất file gốc.
6. Tạo môi trường dependency files.
7. Viết data models và loader.
8. Viết validation input.
9. Viết model index.
10. Viết MILP builder.
11. Viết solver wrapper.
12. Viết solution extraction.
13. Viết independent validation.
14. Viết reporting.
15. Viết CLI và scripts.
16. Viết test.
17. Chạy `pytest -q`.
18. Chạy full Level 1.
19. So sánh kết quả với tham chiếu.
20. Sửa toàn bộ lỗi.
21. Chạy lại test và solver.
22. Viết README cuối.
23. Báo cáo file đã tạo, lệnh đã chạy và kết quả.

Không dừng ở việc chỉ tạo skeleton.

Không yêu cầu người dùng tự hoàn thiện TODO.

Không để `pass`, `NotImplementedError` hoặc placeholder trong đường chạy chính.

---

# 20. Tiêu chí nghiệm thu cuối cùng

Chỉ coi task hoàn thành khi toàn bộ điều sau đúng:

- [ ] Project có đúng cấu trúc chính.
- [ ] Có `requirements.txt`.
- [ ] Cài đặt được trong virtual environment sạch.
- [ ] Dữ liệu được chia `raw` và `processed`.
- [ ] Có đủ 20 kiện và 5 container.
- [ ] Không dùng absolute path.
- [ ] CLI chạy được.
- [ ] Notebook vẫn chạy được.
- [ ] Model có đủ các biến Level 1.
- [ ] Model có đủ các ràng buộc Level 1.
- [ ] Dùng sparse matrix.
- [ ] Solver trả nghiệm khả thi.
- [ ] Nghiệm được validate độc lập.
- [ ] Không kiện nào thiếu hoặc lặp.
- [ ] Không kiện nào vượt biên.
- [ ] Không cặp kiện nào giao nhau.
- [ ] Không container nào quá tải.
- [ ] Instance tham chiếu dùng 2 container.
- [ ] Hai container là C2 và C4.
- [ ] Tổng cost là 1810.
- [ ] Test suite pass.
- [ ] Output CSV/JSON được sinh.
- [ ] README giải thích giới hạn kiện lơ lửng.
- [ ] Không triển khai nhầm Level 2.

---

# 21. Báo cáo cuối Codex phải trả về

Báo cáo theo mẫu:

```text
IMPLEMENTATION STATUS
- Status: COMPLETE / PARTIAL / FAILED
- Python version:
- Dependency installation:

FILES CREATED OR MODIFIED
- ...

COMMANDS EXECUTED
- ...

TEST RESULTS
- pytest result:
- number passed:
- number failed:

SOLVER RESULT
- solver status:
- objective:
- selected containers:
- container count:
- total cost:
- validation valid:
- validation issues:

OUTPUT FILES
- ...

KNOWN LIMITATIONS
- ...
```

Nếu kết quả khác tham chiếu:

- không được tự thay đổi expected result;
- phải kiểm tra dữ liệu, objective, variable indices, Big-M và signs của constraint;
- phải giải thích nguyên nhân rõ ràng.

---

# 22. Cách chạy nhanh notebook hiện tại, không cần Codex refactor

Nếu chỉ muốn chạy code đang có:

1. Giải nén `level1_3dbppsi_bundle.zip` vào một thư mục.
2. Đảm bảo các file sau nằm cùng cấp:

```text
level1_3dbppsi_milp.ipynb
scidb_3dbppsi_items_level1_20.csv
containers_level1_5types.csv
```

3. Mở terminal tại thư mục đó.
4. Tạo môi trường:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install numpy scipy jupyterlab
```

5. Chạy:

```powershell
jupyter lab
```

6. Mở `level1_3dbppsi_milp.ipynb`.
7. Chọn **Run > Run All Cells**.
8. Kết quả mong đợi:

```text
HiGHS Status: Optimal
Used containers: C2, C4
Container count: 2
Validation problems: []
```

Notebook ghi nghiệm mới ra:

```text
level1_solution_from_notebook.csv
```

Nếu chạy notebook từ thư mục khác, hai CSV sẽ không được tìm thấy. Cách đơn giản nhất là giữ notebook và hai CSV cùng một thư mục.

---

# 23. Lỗi thường gặp

## `FileNotFoundError`

Nguyên nhân:

- notebook không nằm cùng CSV;
- terminal mở sai thư mục;
- đổi tên file.

Kiểm tra:

```python
from pathlib import Path
print(Path.cwd())
print(list(Path.cwd().glob("*.csv")))
```

## `ImportError: cannot import name milp`

SciPy quá cũ.

Sửa:

```powershell
pip install --upgrade "scipy>=1.11,<2"
```

## Solver rất lâu

- Chỉ chạy instance 20 kiện.
- Không đổi lên 501 kiện ở Level 1 MILP.
- Kiểm tra không vô tình tạo rotation variables.
- Kiểm tra không vô tình nhân số container theo `availability`.

## Tọa độ có số âm rất nhỏ

Ví dụ:

```text
-2.5e-13
```

Đây là sai số số thực solver. Chuẩn hóa về 0 nếu trị tuyệt đối nhỏ hơn tolerance.

## Nghiệm có kiện lơ lửng

Đây là giới hạn đã biết của Level 1, không phải lỗi overlap.

---

# 24. Chỉ dẫn cuối cho Codex

Hãy triển khai đầy đủ project theo tài liệu này trên codebase hiện tại.

Trước khi sửa code:

- kiểm tra những phần đã tồn tại;
- tái sử dụng logic đúng trong notebook;
- không viết lại vô ích;
- sửa các phần chưa đáp ứng cấu trúc production-like;
- bảo toàn file tham chiếu;
- không thêm Level 2.

Sau khi triển khai:

- chạy test;
- chạy solver;
- validate nghiệm;
- tạo output;
- cập nhật README;
- báo cáo minh bạch mọi phần chưa hoàn thành.
