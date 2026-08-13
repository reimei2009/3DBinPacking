# Corpus MPV fixed-orientation cho Level 2

## Mục đích

Corpus này dùng generator 3D-BPP của Martello, Pisinger và Vigo (MPV) làm
evidence học thuật về hình học. Nó bổ sung cho fixture nhỏ và corpus synthetic
nội bộ; không thay thế chúng.

Level 2 **không** tái tạo hoàn toàn semantics của bài toán MPV gốc:

- orientation bị khóa;
- exact base-support và base-center support của Level 2 là ràng buộc bổ sung;
- MPV không có khối lượng, nên adapter gán mỗi kiện `1 kg` và container có
  payload trung tính đủ lớn;
- vì vậy không được so objective với best-known result MPV gốc.

Official objective của project vẫn là `(số container đã dùng, tổng chi phí)`.
Một kết quả chỉ được ghi nhận khi đủ kiện và validator độc lập trả `VALID`.

## Nguồn và tính toàn vẹn

Trang mã chính thức: <https://hjemmesider.diku.dk/~pisinger/codes.html>.

Bundle `mpv-official-source-v1` gồm `test3dbpp.c`, `3dbpp.c` và
`readme.3dbpp`. Lock nằm tại `config/level_02/mpv_source_lock.yaml`. Checksum
là TOFU lấy qua HTTPS chính thức vào ngày khóa; đây không phải checksum tác giả
công bố. Downloader từ chối URL ngoài host chính thức, checksum sai hoặc bundle
thiếu file; chỉ publish toàn bộ bundle sau khi cả ba file hợp lệ.

Source, executable và dữ liệu sinh không được commit. Build provenance lưu tên
compiler, phiên bản, câu lệnh build, checksum source, adapter và executable.

## Luồng dữ liệu

```text
external/sources (bundle đã khóa)
→ external/imported (bundle đã xác minh)
→ interim/raw_generator_runs (10 native instance cho mỗi tổ hợp)
→ interim/captures (JSON có checksum)
→ interim/normalized/<case> (solver_items.csv, solver_containers.csv)
→ processed/level_02/mpv_fixed_orientation/<case>
→ outputs/level_02/runs (evidence benchmark)
```

`mpv_capture_adapter.c` chỉ cài callback `binpack3d` để ghi hình học native;
không sửa source chính thức, không giải packing và không tạo best-known result.

## Tạo corpus

Cài compiler C trước (ví dụ MinGW-w64 qua MSYS2), mở terminal mới và kiểm tra:

```powershell
gcc --version
```

Sau đó chạy smoke 3 class × 20 kiện:

```powershell
.\.venv\Scripts\python.exe .\scripts\prepare_mpv_academic_corpus.py --mode smoke
.\.venv\Scripts\python.exe .\scripts\run_benchmark_corpus.py `
  --corpus config\level_02\benchmarks\mpv_fixed_orientation_smoke_manual.yaml
```

Khi smoke hợp lệ, materialize đủ 9 class × 20/50/100:

```powershell
.\.venv\Scripts\python.exe .\scripts\prepare_mpv_academic_corpus.py --mode full
.\.venv\Scripts\python.exe .\scripts\run_benchmark_corpus.py `
  --corpus config\level_02\benchmarks\mpv_fixed_orientation_acceptance_manual.yaml
```

Acceptance có 27 case × 2 thuật toán × 2 repeat = 108 execution. Mỗi case chỉ
dùng native instance số 01; 9 instance còn lại được giữ ở `interim` cùng
checksum để audit. Các lần chạy lại chỉ tái dùng raw native run nếu execution
manifest, arguments và checksum đầu ra còn khớp.

## Giới hạn

MPV chỉ chạy bằng CLI trong checkpoint này. Streamlit có thể đọc evidence sau
khi acceptance pass, nhưng không được dùng để chạy MPV tương tác hoặc trộn MPV
với nguồn synthetic đang active.
