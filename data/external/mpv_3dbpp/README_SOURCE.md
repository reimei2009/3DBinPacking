# Nguồn MPV 3D-BPP

Thư mục này lưu provenance cho bộ mã sinh instance 3D bin packing của
Martello–Pisinger–Vigo (MPV). Source C tải từ ngoài và executable biên dịch
trên máy **không được commit**.

Nguồn chính thức: <https://hjemmesider.diku.dk/~pisinger/codes.html>.

## Quy tắc nguồn

- Lock: `config/level_02/mpv_source_lock.yaml`.
- Ba artifact bắt buộc: `test3dbpp.c`, `3dbpp.c`, `readme.3dbpp`.
- SHA-256 trong lock là TOFU từ HTTPS chính thức tại ngày ghi trong lock; tác
  giả không công bố checksum đó. Các lần tải sau bắt buộc khớp lock.
- `sources/` là bản tải bất biến đã kiểm tra checksum.
- `imported/` là bundle đã được importer kiểm tra đủ companion source và ghi
  provenance.
- Không sửa trực tiếp các file dưới `sources/` hoặc `imported/`.

Lệnh tải bundle (không biên dịch, không chạy solver):

```powershell
.\.venv\Scripts\python.exe .\scripts\download_mpv_bundle.py
```

Lệnh tạo corpus Level 2 kiểm tra compiler trước khi tạo instance. Nếu chưa có
`gcc`, `clang` hoặc `cl` trong `PATH`, lệnh dừng với `COMPILER_REQUIRED` và
không tạo corpus chuẩn hóa dở dang.
