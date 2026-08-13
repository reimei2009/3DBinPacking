# Benchmark canonical Level 2

## Benchmark là gì?

Benchmark là một **bộ bài kiểm tra cố định**, kèm quy tắc chạy và cách chấm cố
định. Nó không phải một thuật toán và cũng không phải một lần chạy đơn lẻ.

- Dataset là nguồn tạo đề.
- Case là một bài kiểm tra cụ thể lấy từ dataset.
- Extreme Point Best Fit là baseline: thuật toán mốc để đối chiếu.
- Validator độc lập là bộ phận chấm nghiệm đúng hay sai.
- `best_observed` là nghiệm tốt nhất project đã quan sát trên đúng input; không
  chứng minh tối ưu.

## Nguồn canonical

Benchmark nội bộ dùng duy nhất profile:

```text
level_02_inventory_items_1000_fleet_500_t10_v1
```

Nguồn có 1.000 physical item và 500 physical container thuộc 10 loại C1–C10.
Mọi thuật toán trong cùng case nhận đúng cùng selected-item checksum, catalog
checksum, exact-support rules, container limits và deadline.

## Protocol constructor

File canonical:

```text
config/level_02/benchmarks/generated_1k_500_distribution_corpus.yaml
```

Protocol có sáu quy mô `20, 50, 100, 200, 300, 500`. Mỗi quy mô gồm prefix và
stable-random seed `101, 202, 303`. Ba thuật toán được chạy hai repeat, tổng cộng
24 case và 144 execution. Repair bị tắt để so sánh constructor công bằng.

Số container bắt đầu tìm bằng cận dưới tổng hợp của đúng tập item. Giới hạn tối
đa bằng `max(lower_bound + 2, ceil(1,6 × lower_bound))`, không vượt kho vật lý.
Giá trị đã tính được persist trong resolved corpus và tham gia fingerprint.

Các case 750 và 1.000 nằm trong scale gate riêng:

```text
config/level_02/benchmarks/generated_1k_500_scale_extended_manual.yaml
```

## Repair A/B

File:

```text
config/level_02/benchmarks/canonical_repair_ab_corpus.yaml
```

Best Fit được chạy trên cùng input ở hai treatment: repair tắt và repair bật.
`repair_comparison.csv` báo objective trước/sau, runtime overhead, termination
reason và việc incumbent có được giữ hay không. Runtime không tham gia objective.

## MPV học thuật

MPV là benchmark academic độc lập. View của project dùng fixed orientation,
exact support và adapter weight trung tính, do đó không gộp số liệu MPV với
generated canonical và không tuyên bố so trực tiếp best-known MPV gốc.

## Cách chấm và artifact

Chỉ nghiệm complete và independently `VALID` có official objective:

```text
ít container hơn → nếu bằng nhau thì chi phí thấp hơn
```

Mỗi corpus sinh:

- `results.csv`: từng execution;
- `case_features.csv`: đặc trưng và provenance từng case;
- `pairwise_outcomes.csv`: thắng/hòa/thua trên cùng input fingerprint;
- `distribution_summary.csv`: tỷ lệ hợp lệ, runtime và memory theo quy mô;
- `determinism_evidence.csv`: objective/signature giữa các repeat;
- `repair_comparison.csv`: evidence A/B khi corpus có repair treatment.

Các run mới còn sinh hai bảng trung gian để tránh tổng hợp sai:

- `case_algorithm_summary.csv`: gộp các lần lặp của đúng một bài và một thuật toán;
- `case_differences.csv`: chỉ liệt kê những bài mà các thuật toán cho objective khác nhau.

`p50` được trình bày là **thời gian thường gặp**. `p95` là mức mà khoảng 95% lượt
chạy hoàn thành không lâu hơn giá trị đó. UI chỉ công bố p95 khi một nhóm có ít
nhất 10 lượt chạy; nhóm ít mẫu hơn dùng trung vị và khoảng min–max.

Một case chỉ được tổng hợp với chính các repeat của nó. Giữa nhiều case, project
không lấy trung bình trực tiếp số container, chi phí hoặc encoded objective. Ví dụ,
không được lấy trung bình kết quả 20 kiện với 100 kiện. Phân phối nhiều case dùng:

- WIN/TIE/LOSS trên cùng input fingerprint;
- số container vượt cận dưới tổng hợp và tỷ lệ vượt cận;
- chênh lệch với Best Fit trên đúng case;
- tỷ lệ VALID, timeout, invalid;
- thời gian toàn pipeline, runtime/item và bộ nhớ theo từng quy mô.

Chi phí chỉ được diễn giải như tie-break khi số container bằng nhau. Best Fit là
mốc đối chiếu, không phải optimum được chứng minh.

## Evidence canonical ngày 2026-08-13

Report phát hành nằm tại:

- `docs/reports/manual/level_02_canonical_benchmark_20260813.md`;
- `docs/reports/manual/level_02_canonical_benchmark_20260813.json`.

Report được sinh tự động từ run canonical, không nhập số liệu bằng tay. Gate xác nhận
đủ 24 bài, 144 lượt, 144 nghiệm được validator độc lập xác nhận `VALID` và 72 nhóm
bài–thuật toán cho cùng objective cùng placement signature qua hai lần lặp.

Khi đối chiếu với Extreme Point Best Fit:

- Extreme Point FFD: 0 thắng, 24 hòa, 0 thua;
- Maximal Empty Spaces Best Fit: 1 thắng, 22 hòa, 1 thua.

Hai bài tạo khác biệt là random seed 303 ở quy mô 100 và 500 kiện. Kết quả này là
evidence trên corpus đã khai báo, không chứng minh Best Fit hoặc MES tối ưu trên mọi
bài toán 3D Bin Packing.

Mỗi nhóm thuật toán–quy mô hiện chỉ có 8 lượt. Vì vậy report và UI dùng trung vị cùng
khoảng nhỏ nhất–lớn nhất; không công bố p95 từ số mẫu quá ít. Chất lượng theo quy mô
dùng số container vượt cận dưới tổng hợp, không lấy trung bình raw số container hoặc
chi phí giữa bài 20 kiện và bài 500 kiện.

## Chạy thủ công

```powershell
.\.venv\Scripts\python.exe .\scripts\run_benchmark_corpus.py `
  --corpus config\level_02\benchmarks\generated_1k_500_distribution_corpus.yaml
```

UI chỉ chạy bản quick gồm 6 bài/18 lượt. Corpus canonical đầy đủ gồm 24 bài/144
lượt chạy bằng CLI và UI đọc artifact để tránh khóa web worker. Hai trạng thái độc
lập: quick hoàn thành không có nghĩa canonical đã hoàn thành.

## Dọn evidence cũ

Audit chỉ đọc, không xóa:

```powershell
.\.venv\Scripts\python.exe .\scripts\audit_level2_legacy_benchmarks.py `
  --report-dir data\interim\level_02\audits\legacy_default_source_review
```

Chỉ được xóa sau khi người dùng duyệt manifest chứa đường dẫn, checksum, consumer,
dung lượng, khả năng tái sinh và lý do đề xuất dọn.
