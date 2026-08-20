# Chẩn đoán độ tin cậy deadline MES Level 4–5

Suite này phân biệt MES hết giờ do máy sleep/tải ngoài với operation nội bộ quá dài.
Đây không phải benchmark chất lượng và không tham gia WIN/TIE/LOSS hay canonical evidence.

## Ma trận

Mỗi Level chạy ba input 500 kiện: stable-random seed 101, stable-random seed 307 và
payload pressure. Mỗi input chạy MES ba lần: 9 lượt/Level, tổng 18 lượt. Repair tắt,
deadline 180 giây và validation reserve 3 giây.

```powershell
.\.venv\Scripts\python.exe .\scripts\run_benchmark_corpus.py `
  --corpus config\level_04\benchmarks\mes_deadline_reliability_manual.yaml

.\.venv\Scripts\python.exe .\scripts\run_benchmark_corpus.py `
  --corpus config\level_05\benchmarks\mes_deadline_reliability_manual.yaml
```

Chạy tuần tự và không để máy sleep. Sau đó tạo report:

```powershell
.\.venv\Scripts\python.exe .\scripts\build_mes_deadline_reliability_report.py `
  --level-04-run <thu-muc-run-level-04> `
  --level-05-run <thu-muc-run-level-05> `
  --output-dir docs\reports\manual `
  --expected-source-commit <commit-cua-hai-run>
```

## Cách đọc

- `SYSTEM_SUSPEND_DETECTED`: máy sleep/standby; execution không đủ điều kiện evidence.
- `HOST_CONTENTION_SUSPECTED`: máy active nhưng process nhận rất ít CPU.
- `CLOCK_DISCONTINUITY`: wall clock và monotonic clock lệch bất thường.
- `LONG_NON_INTERRUPTIBLE_OPERATION`: một operation có active-time trên 1 giây.
- `NORMAL`: không có dấu hiệu trên.

Nếu toàn bộ evidence sạch, operation dài nhất không quá 1 giây và overshoot không vượt
1,8 giây thì không sửa cooperative MES. Nếu vượt gate, report chỉ rõ operation để mở
đúng một batch hardening. Chưa dùng subprocess watchdog ở checkpoint này.

## Kết quả chính thức

Hai run ngày 2026-08-20 đạt 18/18 lượt `FEASIBLE + VALID`, 6 nhóm case–algorithm
deterministic và không có execution nhiễu môi trường. Overshoot lớn nhất bằng 0 giây;
operation dài nhất là `exact_support`, khoảng 0,01093 giây. Quyết định là
`NO_COOPERATIVE_HARDENING_REQUIRED`: không cần sửa cooperative deadline hoặc thêm
subprocess watchdog.

Kết quả này không thay đổi quyết định Portfolio V1 `NOT_PROMOTED`. Report có checksum và
provenance đầy đủ nằm tại
[MES deadline reliability ngày 2026-08-20](../reports/manual/mes_deadline_reliability_20260820.md).
