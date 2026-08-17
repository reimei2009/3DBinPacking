# A/B Contact/Support Index cho Level 4–5

## Mục đích

Benchmark này đo riêng tác động của broad-phase index trong construction. Hai
variant dùng cùng items, kho container, ràng buộc, start/max, deadline và seed.
Repair tắt. Official objective vẫn là số container rồi chi phí.

Mỗi Level có 6 input ghép cặp:

- stable-random seed 101 tại 100, 300 và 500 kiện;
- `largest_volume`, `heaviest` và `payload_pressure` tại 500 kiện.

Hai variant × ba constructor × ba repeat tạo 108 lượt cho mỗi Level. Runner xen
kẽ thứ tự variant theo cặp để giảm bias do cache và nhiệt độ máy.

## Kết quả V1

V1 hoàn thành `108/108 VALID` ở từng Level và giữ nguyên status, objective,
placement signature cùng rejection counters. Tuy nhiên V1 không đạt gate hiệu
năng:

- Level 4: construction cải thiện trung vị 6,92%, thấp hơn gate 20%; có ba cặp
  construction regression;
- Level 5: construction chậm hơn trung vị 1,11%; có sáu cặp construction
  regression;
- memory overhead vẫn dưới giới hạn.

Vì manifest nguồn có `git_dirty=true`, hai run chỉ là diagnostic evidence, không
phải release evidence. Báo cáo versioned nằm tại
`docs/reports/manual/contact_support_index_ab_v1_20260817.md`.

## Chạy V2 thủ công

Chạy tuần tự, không chạy song song:

Trước benchmark dài, có thể định vị overhead của V1 trên đúng bốn cặp đại diện
(12 lượt mỗi Level, tổng 24 lượt). Kết quả này chỉ là chẩn đoán và không tham gia
ranking:

```powershell
.\.venv\Scripts\python.exe .\scripts\profile_contact_support_index.py `
  --level level_04 `
  --source-run-dir outputs\level_04\runs\20260817T040619737881Z__level_04__benchmark_corpus__level_04_contact_support_index_ab_v1__seed42

.\.venv\Scripts\python.exe .\scripts\profile_contact_support_index.py `
  --level level_05 `
  --source-run-dir outputs\level_05\runs\20260817T050431203215Z__level_05__benchmark_corpus__level_05_contact_support_index_ab_v1__seed42
```

Sau đó chạy A/B V2 từ một commit sạch:

```powershell
.\.venv\Scripts\python.exe .\scripts\run_benchmark_corpus.py `
  --corpus config\level_04\benchmarks\contact_support_index_v2_ab_manual.yaml

.\.venv\Scripts\python.exe .\scripts\run_benchmark_corpus.py `
  --corpus config\level_05\benchmarks\contact_support_index_v2_ab_manual.yaml
```

Kết quả so sánh nằm tại:

```text
outputs/<level>/runs/<run_id>/benchmark/contact_index_comparison.csv
```

## Cách đọc gate

`correctness_gate_passed` phải đúng cho mọi hàng. Status, objective, placement
signature và rejection counters giữa hai variant phải giống nhau. Sau đó mới đọc
construction speedup, wall-runtime speedup và memory overhead.

Chỉ promote mặc định khi từng Level đạt đồng thời:

- median construction toàn Level giảm ít nhất 20%;
- wall runtime median không tăng;
- không constructor nào tăng construction quá 5%;
- peak memory tăng không quá 20%;
- mọi nghiệm thành công independently `VALID` và deterministic.

Artifact A/B là research evidence, không được gộp vào ranking canonical. Chỉ
promote khi **cả hai Level** đạt gate. Nếu một Level không đạt, V2 được ghi
`NOT_PROMOTED`, mặc định tiếp tục tắt và không phát triển V3.
