# Profiling runtime Benchmark V2 Level 2

## Mục đích

Profiling dùng để trả lời **thời gian đang bị tiêu tốn ở đâu** trước khi sửa thuật toán.
Nó là phép đo chẩn đoán, không phải benchmark chất lượng và không tham gia xếp hạng
WIN/TIE/LOSS.

Quy trình chỉ được chạy sau khi cả ba tầng Benchmark V2 đã hoàn thành và report tổng
hợp trả `PASS`:

1. random distribution;
2. stress;
3. prefix regression.

## Hai cấp đo

### Cấp phase

Cấp này đọc telemetry của run V2 không gắn profiler, vì vậy phản ánh runtime chính thức.
Các phase được tách thành chuẩn bị dữ liệu, precheck/cận dưới, construction, improvement,
validation và reporting. Phần thời gian chưa gán chắc chắn được ghi là `unattributed`,
không âm thầm cộng vào phase khác.

### Cấp function

Cấp này chạy lại một tập case nhỏ bằng `cProfile` để xác định hàm Python tiêu tốn nhiều
thời gian. `cProfile` tạo overhead, vì vậy thời gian của nó chỉ dùng chẩn đoán; không được
so với runtime benchmark chính thức.

Tập chẩn đoán gồm:

- random seed 101 ở 100, 300 và 500 kiện;
- `largest_volume`, `heaviest`, `payload_pressure` ở 500 kiện;
- tối đa hai bài có chênh lệch objective lớn nhất trong cả ba tầng V2;
- ba constructor, một lần chạy cho mỗi bài.

Việc chọn bài là deterministic và loại trùng theo `case_id`.

## Cách chạy

Sau khi có ba run directory V2:

```powershell
.\.venv\Scripts\python.exe .\scripts\profile_level2_benchmark.py `
  --random-run-dir <thu-muc-run-random> `
  --stress-run-dir <thu-muc-run-stress> `
  --prefix-run-dir <thu-muc-run-prefix>
```

Command không tạo solver mới. Nó dựng lại `ExperimentRequest` từ request đã lưu trong
artifact V2 và gọi đúng pipeline Level 2 hiện hành.

## Output

Mỗi lần profiling tạo một thư mục độc lập:

```text
outputs/level_02/runs/<run_id>__level_02__benchmark_profile__seed42/
```

Các file chính:

- `profile_manifest.json`: nguồn V2, danh sách case, trạng thái và quyết định sơ bộ;
- `phase_profile.csv`: thời gian chính thức theo phase;
- `function_profile.csv`: self-time và cumulative-time theo hàm;
- `profiles/*.pstats`: dữ liệu gốc của `cProfile`;
- `decision_gate.json`: tỷ trọng và hướng ưu tiên;
- `reports/summary.md`: tóm tắt tiếng Việt.

Manifest luôn ghi `diagnostic_only=true` và
`eligible_for_benchmark_ranking=false`, nên run profiling không được đưa vào evidence
canonical hoặc biểu đồ chất lượng.

## Điều kiện ra quyết định

- Reporting từ 30% wall time: ưu tiên đường ghi artifact/report/visualization.
- Construction từ 30% wall time:
  - overlap và exact-support trên 40% self-time của construction: thiết kế
    spatial/contact index;
  - EP generation/candidate enumeration trên 40%: thiết kế cache, pruning hoặc
    candidate ordering;
  - không có thành phần chi phối: chưa tối ưu vi mô.
- Chỉ mở A/B chất lượng khi V2 có khác biệt ghép cặp hoặc repair pilot tạo objective WIN.

Trước khi phát hành report, profiler còn kiểm tra nghiệm chạy có cùng checksum item,
official objective và placement signature với nghiệm V2 không gắn profiler. Nếu khác,
run profiling trả `FAIL` thay vì đưa ra kết luận bottleneck.

## Giới hạn

- Profiling không chứng minh thuật toán tối ưu.
- Aggregate lower bound chỉ dựa tải trọng/thể tích, không chứng minh khả thi hình học.
- Tỷ trọng theo function của `cProfile` có overhead và chỉ dùng để định vị khu vực cần
  điều tra tiếp.
- V1 vẫn là canonical cho tới khi V2 được promote bằng checkpoint riêng.

## Kết quả đo ngày 2026-08-13

Benchmark V2 đã hoàn thành đủ 84 bài, 756 lượt chạy và 252 nhóm kiểm tra tính xác
định. Tầng random được phục hồi bằng một artifact mới: 539 lượt `VALID` được giữ
nguyên và đúng một lượt bị lỗi publish trên Windows được chạy lại. Output lịch sử
không bị sửa.

Profiling 8 bài/24 lượt xác định reporting và xuất artifact chiếm trung vị 56,5%
wall time; construction chiếm 26,8%. Support/overlap và candidate enumeration đều
chưa vượt gate tối ưu solver. Điểm tốn thời gian lớn nhất trong reporting là việc
chạy lại `git status` và băm cùng source tree cho từng child run của corpus.

Runtime provenance vì vậy được snapshot một lần cho mỗi project root trong cùng
process. Mỗi manifest vẫn nhận một defensive copy đầy đủ; corpus không được phép
thay đổi source trong khi đang chạy. Đo lại cùng 24 lượt profiling cho kết quả:

- tổng wall time: 334,39 giây xuống 239,68 giây;
- mức giảm: 28,3%;
- objective, item checksum và placement signature không đổi;
- cả hai profiling run đều `PASS` và không tham gia ranking benchmark.

Kết quả này vượt gate giảm 20–25% phase mục tiêu. Không có cơ sở để sửa heuristic
hoặc thêm spatial index tại checkpoint này.
