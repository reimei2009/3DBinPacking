# Corpus nghiên cứu Level 1

Corpus local chuẩn nằm tại `config/level_01/benchmarks/research_corpus.yaml`.

| Case | Nhóm | Mục đích | Mốc tham chiếu |
|---|---|---|---|
| `small_easy_i5_c2` | nhỏ | regression nhanh và quality gap chính xác | MILP |
| `small_tight_i10_c2` | nhỏ | nghiệm khả thi sát giới hạn tải trọng | MILP |
| `small_infeasible_i10_c1` | nhỏ | bất khả thi tổng tải trọng | chứng minh MILP |
| `medium_mixed_i50_c8` | vừa | so sánh heuristic local | best-observed |
| `large_scalability_i100_c15` | lớn | kiểm tra khả năng mở rộng CPU | best-observed |

Chạy corpus bằng lệnh:

```powershell
python scripts\run_benchmark_corpus.py --corpus config/level_01/benchmarks/research_corpus.yaml
```

Mỗi case dùng số dòng prefix đã khai báo từ CSV nguồn bất biến và catalog container deterministic của Level 1. Corpus không đại diện thống kê cho mọi phân phối 3D Bin Packing. Vai trò của nó là regression có thể tái lập, đo exact gap trên instance nhỏ, kiểm tra failure semantics và theo dõi khả năng mở rộng local. Benchmark family mới phải dùng corpus có version và provenance riêng, không sửa âm thầm corpus này.

Phải đọc `references.csv` trước khi so sánh gap. `proven_optimal` và
`proven_infeasible` chỉ đến từ MILP exact. `best_observed` là nghiệm hợp lệ tốt
nhất quan sát được trong lần chạy corpus trên cùng input fingerprint, không phải
chứng minh tối ưu và có thể được cải thiện sau này. `best_known` chỉ còn là nhãn
legacy khi đọc artifact cũ.

## Nguồn MPV bên ngoài

Script `scripts/prepare_mpv_academic_corpus.py` điều phối bundle MPV đã khóa
checksum, build local và chuẩn hóa corpus. Pytest không gọi Internet hoặc compiler
thật. Source, executable và dữ liệu sinh không được commit; lock, provenance,
adapter và cấu hình được version hóa.

Semantics gốc có thể cho phép rotation. Level 1–2 chỉ dùng fixed-orientation
view, nên kết quả nội bộ không được tuyên bố tương đương best-known gốc nếu chưa
chứng minh hai contract giống nhau.
