# Chạy ứng dụng nghiên cứu Streamlit 3D

## Tìm kiếm trên kho container và cải thiện incumbent

Khi bật tìm container tốt nhất trong toàn bộ kho, số container trên UI là giới
hạn được phép sử dụng, không phải prefix của catalog. Pipeline luôn chạy
capacity precheck và dựng một incumbent đã qua independent validation.

Checkbox **Cải thiện nghiệm sau construction** điều khiển riêng pha repair.
Giá trị mặc định kế thừa profile đang chọn. Khi bật, người dùng chọn ngân sách
3, 10, 30 giây hoặc tùy chỉnh; ngân sách này luôn nằm trong global search
deadline và không chiếm validation reserve. Repair thử relocation,
support-closure ở Level 2, partial repack, container elimination và bounded
rebuild. Khi tắt, construction và final validation vẫn chạy nhưng không có
post-construction improvement.

Với Level 1–2 inventory-aware, **Best Fit** là lựa chọn khuyến nghị khi ưu tiên
ít container/chi phí; **FFD** là comparator nhanh. Hai thuật toán chạy độc lập,
không tự fallback qua lại.

Kết quả UI hiển thị số container và chi phí trước/sau repair, runtime, số
candidate, cận aggregate và lý do dừng. `NO_VALID_CLUSTER_REPACK` hoặc
`heuristic_consolidation_failed` chỉ có nghĩa heuristic chưa cải thiện được
incumbent; không phải chứng minh không tồn tại nghiệm dùng ít container hơn.
Nếu hết thời gian, validated incumbent ban đầu được giữ nguyên.

Với adaptive cluster, UI còn hiển thị các neighborhood đã thử và số target có
failed-item evidence. Planner xét destination có extreme point sẵn và cả
destination giàu tải trọng/thể tích cần partial repack; cluster một, hai và ba
đích có quota riêng. UI cũng phân biệt khoảng trống hình học với trường hợp
payload gần đầy, đồng thời hiển thị lý do target chưa đóng được. Các reason này
là kết quả tìm kiếm bounded, không phải chứng minh bất khả thi.

## Windows

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
python scripts\run_web_app.py
```

Open the local URL printed by Streamlit, normally `http://localhost:8501`.

The default language is Vietnamese. Use **Ngôn ngữ / Language** in the sidebar to switch to English. The **Mô hình toán học** tab renders the active level's notation, variables, objective, and constraints with LaTeX and shows the canonical source-code mapping for each expression.

## Linux

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
python scripts/run_web_app.py
```

## Workflow

1. Select an implemented level (`level_01` or `level_02`).
2. Select a compatible algorithm.
3. Enter item count, container count, seed, environment metadata, and algorithm-specific settings.
   In Level 2, the **Minimum supported-area ratio α** control overrides
   `support.threshold` for that one run. Its valid range is `0.01` to `1.00`;
   the default is `0.80`. The selected value is written to the run's
   `resolved_config.yaml` and manifest metadata. Base-center support remains
   mandatory under the Level 2 contract.
4. Click **Run experiment**.
5. Review solver status and independent validation status.
6. Inspect the combined scene or one used container.
7. Open previous immutable runs from **Run history**.

## 3D display controls

- The default view opens the first used container rather than the combined scene.
- **Rõ khối / Solid** dùng opacity `1.00` và là chế độ mặc định.
- **Cân bằng / Balanced** uses opacity `0.75`.
- **X-Ray** uses opacity `0.30`.
- The opacity slider supports manual values from `0.20` to `1.00`.
- Selecting an item renders it at opacity `1.00`, dims other visible items to `0.20`, adds a dark outline, and shows its position, dimensions, and weight.
- **Ẩn các kiện / Hide items** temporarily removes selected items from the view.

These controls change presentation only. They never modify `scene.json`, placements, validation, metrics, or solver output.

Every execution uses the same pipeline as the CLI and writes to a new directory under `outputs/<level>/runs/<run_id>/`. The UI never overwrites an earlier run.

## Level 8 logistics demo

The UI distinguishes four data profiles:

- Quick logistics fixture: 6 items / 2 containers / 3 stops;
- Logistics semantics fixture: 20 items / 5 small fixture containers / 3 stops;
- Cross-level comparison: 20 public items with the same C1-C5 catalog used by
  Levels 1-7 and five declared delivery stops;
- Synthetic research: custom up to 100 items / 10 containers / 5 stops.

Only compare runs when dataset ID, container catalog ID, selected-item
checksum, selection strategy, and seed all match. The sidebar displays these
identifiers and previews container dimensions, volume, payload, and cost.

Without `GOOGLE_ROUTES_API_KEY`, only deterministic offline routing is shown.
It follows declared delivery priority, calculates Haversine straight-line
distance, and estimates duration at 35 km/h. It does not use a road network,
traffic data, billing account, or external API.

Choose either `prefix` or deterministic `stable_random` item selection. The
research dataset and its generator manifest/checksums are tracked under
`data/raw/level_08/web_demo/`; 300-item cases remain CLI-only.

The default stop CSV can be replaced by an uploaded CSV containing one depot
and at most ten delivery stops. The file is checksummed and copied into the
immutable run. Route order always follows declared delivery priority; the UI
does not optimize waypoints.

When sequential replay is enabled, its persisted event stream supplies the
play/pause, previous/next, slider, speed, current stop, highlighted map marker,
and 3D item visibility. This remains deterministic offline replay, not
equipment, staging-space, GPS, or real-time simulation.

## Benchmark trên nguồn dữ liệu đang chọn

Mỗi Level chỉ có một **Nguồn dữ liệu và kho container** đang hoạt động. Lựa chọn này
nằm ở đầu sidebar và được dùng chung cho thí nghiệm đơn, benchmark, capacity precheck
và bộ lọc lịch sử. Đổi thuật toán không đổi nguồn. Nếu thuật toán không hỗ trợ cách
tìm kiếm của nguồn đang chọn, UI dừng và giải thích; hệ thống không tự quay về dataset
mặc định.

Sidebar và benchmark có thể dùng số lượng khác nhau nhưng vẫn đọc cùng nguồn. Ví dụ,
với nguồn 1.000 kiện / kho 500 container, thí nghiệm đơn có thể chạy 100 kiện trong khi
benchmark chạy 1.000 kiện. Các ô số lượng là ô nhập tự do trong phạm vi dữ liệu thật,
không phải preset khóa cứng.

Benchmark tương tác chỉ có một thao tác **Kiểm tra và chạy benchmark**:

1. chọn thuật toán, số kiện và cách lấy kiện;
2. nhập số container bắt đầu, số tối đa được dùng và thời gian;
3. tùy chọn bật cải thiện nghiệm; seed, repeat và ngân sách chi tiết nằm trong
   **Thiết lập nâng cao**;
4. nhấn nút chạy; UI chụp đúng giá trị hiện tại, resolve lại nguồn, kiểm tra capacity
   và provenance rồi mới thực thi.

Widget benchmark không nằm trong `form`: thay đổi số kiện, start/max hoặc cách lấy kiện
sẽ cập nhật precheck ngay. Không có draft chạy ẩn và không có bước chạy thứ hai dùng
state cũ. Khi đổi nguồn, các giá trị vượt giới hạn của nguồn trước được loại bỏ.

Khi mọi thuật toán được chọn đều hỗ trợ shared inventory, benchmark tự tìm trong toàn
bộ catalog; start/max luôn có hiệu lực và không phụ thuộc checkbox của thí nghiệm đơn.
Không được trộn inventory-aware solver với thuật toán chỉ hỗ trợ fixed subset trong cùng
một phép so sánh.

Thay đổi bất kỳ tham số nào sau một lần chạy sẽ ẩn kết quả vừa chạy. Kết quả lịch sử
mặc định chỉ gồm các run có cùng profile và checksum; muốn xem nguồn khác phải bật lựa
chọn lịch sử riêng, và các run đó luôn được đánh dấu là kết quả đã lưu trước đây.

Với Level 1–2 dùng kho container, tổng số container trong kho là lượng có thể lựa chọn,
không phải số bắt buộc phải dùng. **Số container bắt đầu tìm** là điểm bắt đầu của
heuristic; **Số container tối đa được dùng** là giới hạn cứng. Nếu giới hạn cứng nhỏ
hơn cận tổng hợp theo thể tích hoặc tải trọng, UI khóa chạy và giải thích rằng sức chứa
chắc chắn không đủ. Precheck đạt chỉ chứng minh đủ sức chứa tổng hợp, chưa chứng minh
có thể xếp hợp lệ về hình học hoặc hỗ trợ đáy.

Mỗi thuật toán có giới hạn thời gian riêng. UI tính tổng thời gian xấu nhất từ số thuật
toán, số seed, số lần lặp và giới hạn của mỗi thuật toán. Benchmark từ 500 kiện, thời
gian xấu nhất trên năm phút hoặc chế độ không giới hạn đều cần xác nhận riêng. Repair
có ngân sách riêng và không được chiếm thời gian dành cho kiểm định cuối.

Dashboard một case chỉ hiển thị validity, số container, chi phí và runtime. Dashboard
nhiều case có ba khu vực: **Tổng quan**, **Chất lượng**, và **Thời gian và độ tin cậy**.
Không cộng hoặc lấy trung bình raw container/objective giữa các quy mô khác nhau.

Trên Level 2, tab benchmark được chia thành:

- **So sánh tùy chỉnh**: người dùng chọn số kiện, thuật toán, giới hạn container,
  runtime và repair trên nguồn đang hoạt động. Kết quả không thay đổi benchmark chuẩn.
- **Benchmark chuẩn**: protocol cố định 24 case; UI chỉ chạy bản quick 18 execution
  và đọc artifact của bản đầy đủ chạy bằng CLI.
- **Benchmark học thuật MPV**: chỉ đọc evidence riêng, không gộp với nguồn generated.

UI dùng thời gian toàn pipeline làm thời gian chính vì đó là thời gian người dùng thực
sự chờ. Runtime riêng của solver chỉ nằm trong chi tiết kỹ thuật. `p95` chỉ xuất hiện
khi một nhóm có ít nhất 10 lượt; benchmark nhanh ít mẫu hiển thị trung vị và min–max.
Biểu đồ phân phối không xuất hiện khi chỉ có một input fingerprint. Chất lượng được
đọc theo thứ tự: nghiệm hợp lệ, ít container, chi phí thấp hơn khi cùng số container.

Sau khi cập nhật source, phải khởi động lại Streamlit để tránh tiến trình cũ giữ module
hoặc cấu hình đã lưu trong bộ nhớ.

## Important Level 1 limitation

The 3D view is a geometric and payload visualization. It is not evidence of physical stability because Level 1 does not model gravity, support, stacking, fragility, center of gravity, or load/unload order.
## Benchmark sử dụng snapshot nguyên tử

Ở Level 1–2, nguồn dữ liệu được chọn một lần và được dùng chung cho thí nghiệm đơn,
benchmark, precheck và lịch sử. Phần benchmark nằm trong một form nguyên tử: chỉ khi
nhấn **Kiểm tra và chạy benchmark**, toàn bộ số kiện, container bắt đầu, giới hạn tối
đa, seed, runtime và repair mới được chụp thành một request bất biến. Giá trị hiển thị
trong các ô nhập phải trùng với `benchmark/request.json`; ứng dụng không được tự đổi
giới hạn container sang giá trị trong config cũ.

Nguồn mặc định của Level 2 là corpus nghiên cứu 1.000 kiện/500 container. Fixture
501/5 vẫn được giữ để kiểm tra nhanh. Mỗi nguồn áp dụng giới hạn theo số dòng và số
physical container thực sự tồn tại; đổi nguồn sẽ reset các widget không còn hợp lệ.

Nguồn 20.000 kiện/5.000 container chỉ xuất hiện sau khi hoàn thành ba bước thủ công:

```powershell
.\.venv\Scripts\python.exe .\scripts\materialize_level2_solver_research.py

.\.venv\Scripts\python.exe .\scripts\run_benchmark.py `
  --suite config\level_02\benchmarks\solver_research_i20000_f5000_web_gate_manual.yaml

.\.venv\Scripts\python.exe .\scripts\qualify_level2_large_web_profile.py `
  --run-dir outputs\level_02\runs\<benchmark_run_id>
```

Materializer tạo view deterministic từ corpus 100.000/5.000 nhưng không sửa dữ liệu
gốc. Gate chỉ chấp nhận nghiệm `VALID` hoặc timeout rõ ràng không có objective, kiểm
tra deterministic repeat và peak memory trước khi tạo `web_qualification.json`.
Benchmark lớn không bảo đảm tìm được nghiệm trong deadline.
